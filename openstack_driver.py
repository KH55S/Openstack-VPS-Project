import openstack
import requests
import time
from openstack.connection import Connection
from datetime import datetime, timedelta, timezone

class OpenStackManager:
    # clouds.yaml을 사용하여 인증 정보 외부화
    # 보안 및 유지보수를 위해 SDK의 Connection 프로토콜 활용
    def __init__(self, cloud_name='my-openstack'):
        self.conn = openstack.connect(cloud=cloud_name)
        
    def get_network_info(self):
        # Neutron API를 호출해 현재 활성화된 네트워크와 서브넷 조회
        networks = list(self.conn.network.networks())
        return networks
    
    def get_compute_quotas(self, project_name='admin'):
        # Nova API를 호출해 프로젝트의 CPU/RAM 할당량 확인
        # 사용량 요약 기능을 위한 데이터 소스
        project = self.conn.identity.find_project(project_name)
        limits = self.conn.compute.get_limits(project=project.id)
        return limits.absolute

    def create_vps_with_access(self, instance_name, project_id, network_id, image_name, flavor_name, key_name):
        # 인스턴스 생성 후 접속용 Floating IP까지 자동 매핑
        try:
            # 대상 프로젝트에 대한 프록시 연결 생성 (관리자 권한 필요): 해당 프로젝트의 쿼터와 권한 내에서 생성
            target_conn = self.conn.connect_as(project_id=project_id)
            
            # 자원 찾기
            image = target_conn.compute.find_image(image_name)
            flavor = target_conn.compute.find_flavor(flavor_name)
            
            # 보안 그룹 생성
            sg_name = f"{instance_name}-sg"
            sg = self.create_security_group_with_rules_in_project(target_conn, sg_name)
            
            # 서버 생성
            server = target_conn.compute.create_server(
                name=instance_name,
                image_id=image.id,
                flavor_id=flavor.id,
                networks=[{"uuid": network_id}],
                key_name=key_name,
                security_groups=[{"name": sg.name}]
            )
            
            # ACTIVE 상태 대기
            server = target_conn.compute.wait_for_server(server)
            print(f"인스턴스 활성화 완료 : {server.id}")
            
            # Floating IP 처리 초기화
            fip_addr = "N/A"
            ext_nets = list(target_conn.network.networks(name="ext_net"))
            
            if ext_nets:
                ports = list(target_conn.network.ports(device_id=server.id))
                if ports:
                    port_id = ports[0].id
                    fip = target_conn.network.create_ip(
                        floating_network_id=ext_nets[0].id,
                        port_id=port_id
                    )
                    fip_addr = fip.floating_ip_address
                    print(f"Floating IP 연결 완료 : {fip_addr}")
            
            # Fixed IP 추출 (네트워크 이름을 몰라도 첫 번째 사설 IP를 가져옴)
            fixed_ip = "N/A"
            for net_addresses in server.addresses.values():
                for addr in net_addresses:
                    if addr.get('OS-EXT-IPS:type') == 'fixed':
                        fixed_ip = addr['addr']
                        break

            return {
                "instance_id": server.id,
                "project_id": project_id,
                "fixed_ip": fixed_ip,
                "floating_ip": fip_addr,
                "status": "ACTIVE"
            }
        except Exception as e:
            print(f"[프로젝트별 인스턴스 생성 오류] : {e}")
            raise e


    def create_security_group_with_rules_in_project(self, target_conn, sg_name):
        # 전용 보안 그룹 생성 및 필수 규칙(SSH, ICMP, 9100) 추가
        
        # 기존 보안 그룹 확인
        existing_sg = target_conn.network.find_security_group(sg_name)
        if existing_sg:
            return existing_sg
        
        # 보안 그룹 생성 및 규칙 추가
        print(f"--- 보안 그룹 {sg_name} 생성 중... ---")
        sg = target_conn.network.create_security_group(name=sg_name)
        
        target_conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction='ingress',
            ethertype='IPv4',
            protocol='tcp',
            port_range_min=22,
            port_range_max=22
        )
        
        target_conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction='ingress',
            ethertype='IPv4',
            protocol='icmp'
        )
        
        # node-exporter
        target_conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction='ingress',
            ethertype='IPv4',
            protocol='tcp',
            port_range_min=9100,
            port_range_max=9100
        )
        
        return sg



    def get_instance_metrics(self, prometheus_url, instance_ip):
        # 프로메테우스 API를 호출해 특정 인스턴스(IP)의 CPU / 메모리 / Disk I/O 메트릭 조회
        
        if instance_ip == "N/A":
            return {"cpu": "No Data", "memory": "No Data", "disk_read": 0, "disk_write": 0}
        
        queries = {
            "cpu": f'100 - (avg by (instance) (irate(node_cpu_seconds_total{{instance=~"{instance_ip}:.*", mode="idle"}}[1m])) * 100)',
            "memory": f'(1 - (node_memory_MemAvailable_bytes{{instance=~"{instance_ip}:.*"}} / node_memory_MemTotal_bytes{{instance=~"{instance_ip}:.*"}})) * 100',
            "disk_read": f'sum(rate(node_disk_read_bytes_total{{instance=~"{instance_ip}:.*"}}[1m]))',
            "disk_write": f'sum(rate(node_disk_written_bytes_total{{instance=~"{instance_ip}:.*"}}[1m]))'
        }
        
        results = {}
        for key, q in queries.items():
            try:
                response = requests.get(f"{prometheus_url}/api/v1/query", params={'query': q}, timeout=2)
                data = response.json()
                
                if data['status'] == 'success' and data['data']['result']:
                    val = float(data['data']['result'][0]['value'][1])
                    # 디스크 I/O는 KB/s 단위로 변환, 나머지는 소수점 둘째자리 반올림
                    results[key] = round(val / 1024, 2) if "disk" in key else round(val, 2)
                else:
                    results[key] = "No Data" if "disk" not in key else 0
            except Exception as e:
                print(f"Metrics Error ({key}): {e}")
                results[key] = "Error"
        return results
        
        
    def get_unified_dashboard_data(self, prometheus_url):
        # 오픈스택 인스턴스 정보와 프로메테우스 메트릭 통합
        try:
            # all_projects=True : 다른 프로젝트의 인스턴스까지 보이도록
            instances = list(self.conn.compute.servers(all_projects=True))
            
            unified_data = []
            
            for server in instances:
                fixed_ip = "N/A"
                floating_ip = "N/A"

                # 모든 네트워크 정보를 돌며 Fixed와 Floating IP를 구분해서 추출
                for net_name, addr_list in server.addresses.items():
                    for addr in addr_list:
                        if addr.get('OS-EXT-IPS:type') == 'floating':
                            floating_ip = addr['addr']
                        elif addr.get('OS-EXT-IPS:type') == 'fixed':
                            fixed_ip = addr['addr']
                
                metrics = self.get_instance_metrics(prometheus_url, floating_ip)
                
                unified_data.append({
                    "instance_id": server.id,
                    "name": server.name,
                    "status": server.status,
                    "project_id": server.project_id,
                    "fixed_ip": fixed_ip,
                    "floating_ip": floating_ip,
                    "cpu": metrics["cpu"],
                    "memory": metrics["memory"],
                    "disk_read": metrics["disk_read"],
                    "disk_write": metrics["disk_write"],
                    "created_at": server.created_at
                })
            return unified_data
        except Exception as e:
            print(f"Dashboard 데이터 통합 중 오류 발생 : {e}")
            return []
        
        
        
    def delete_instance(self, instance_id):
        try:
            server = self.conn.compute.get_server(instance_id)
            project_id = server.project_id
            instance_name = server.name
            sg_name = f"{instance_name}-sg"
            
            target_conn = self.conn.connect_as(project_id=project_id)
            
            # floating IP 정리
            ports = list(target_conn.network.ports(device_id=instance_id))
            for port in ports:
                fips = list(target_conn.network.ips(port_id=port.id))
                for fip in fips:
                    print(f"Floating IP 제거 중 : {fip.floating_ip_address}")
                    target_conn.network.delete_ip(fip.id)
                    
            # 인스턴스 삭제
            print(f"인스턴스 삭제 요청 : {instance_id}")
            target_conn.compute.delete_server(instance_id)
            
            # 보안그룹 삭제 전 인스턴스 삭제 대기
            target_conn.compute.wait_for_delete(server, wait=25)
            
            # 보안그룹 삭제
            sg = target_conn.network.find_security_group(sg_name)
            if sg:
                print(f"인스턴스와 연결된 보안그룹 삭제 중 : {sg_name}")
                target_conn.network.delete_security_group(sg.id)
                print("[ 모든 자원 정리 완료] ")
                
            return True
        except Exception as e:
            print(f"인스턴스 삭제 오류 : {e}")
            raise e


    def setup_tenant_infrastructure(self, username):
        # 신규 유저를 위한 프로젝트/네트워크/서브넷/라우터 생성 + 키 페어
        try:
            print(f"{username}을 위한 테넌트 인프라 구축")
            
            # 프로젝트 생성
            project_name = f"{username}_Project"
            project = self.conn.identity.create_project(
                name=project_name,
                description=f"Project for {username}",
                domain_id="default"
            )
            project_id = project.id
            
            # 네트워크 생성
            net_name = f"{username}_net"
            network = self.conn.network.create_network(
                name=net_name,
                project_id=project_id
            )
            network_id = network.id
            
            # 서브넷 생성
            subnet_name = f"{username}_subnet"
            subnet = self.conn.network.create_subnet(
                name=subnet_name,
                network_id=network_id,
                project_id=project_id,
                ip_version=4,
                cidr="10.0.0.0/24",
                gateway_ip="10.0.0.1",
                dns_nameservers=["8.8.8.8"]
            )
            
            # 라우터 생성 및 외부망 게이트웨이 설정
            router_name = f"{username}_router"
            ext_net = self.conn.network.find_network("ext_net")
            
            router = self.conn.network.create_router(
                name=router_name,
                project_id=project_id,
                external_gateway_info={"network_id": ext_net.id}
            )
            
            # 라우터와 서브넷 연결 (인터페이스 추가)
            self.conn.network.add_interface_to_router(
                router.id,
                subnet_id=subnet.id
            )
            
            # 키 페어 생성
            key_name = f"{username}_key"

            keypair = self.conn.compute.create_keypair(name=key_name)
            print(f"{username} 인프라 구축 완료 (Project: {project_id})")
            
            return {
                "project_id": project_id,
                "network_id": network_id,
                "project_name": project_name,
                "key_name": key_name,
                "private_key": keypair.private_key
            }
            
        except Exception as e:
            print(f"인프라 자동 구축 실패 : {e}")
            raise e


    def get_host_resource_usage(self, prometheus_url):
        host_label = 'instance=~"localhost:9100.*"' 
        
        queries = {
            "cpu_load": f"node_load1{{{host_label}}}",
            "cpu_usage": f"100 - (avg by (instance) (irate(node_cpu_seconds_total{{{host_label}, mode='idle'}}[1m])) * 100)",
            "mem_usage": f"(1 - (avg by (instance) (node_memory_MemAvailable_bytes{{{host_label}}}) / avg by (instance) (node_memory_MemTotal_bytes{{{host_label}}}))) * 100",
            "disk_usage": f"100 - (sum by (instance) (node_filesystem_avail_bytes{{{host_label}, mountpoint='/etc/hosts'}}) / sum by (instance) (node_filesystem_size_bytes{{{host_label}, mountpoint='/etc/hosts'}}) * 100)",
            "net_throughput": f"(sum(rate(node_network_receive_bytes_total{{{host_label}, device!~'lo|veth.*|docker.*|br.*|tap.*'}}[1m])) + sum(rate(node_network_transmit_bytes_total{{{host_label}, device!~'lo|veth.*|docker.*|br.*|tap.*'}}[1m]))) * 8 / 1024 / 1024",
            "disk_iops": f"sum(rate(node_disk_reads_completed_total{{{host_label}}}[1m])) + sum(rate(node_disk_writes_completed_total{{{host_label}}}[1m]))"
        }
        
        results = {}
        for key, q in queries.items():
            try:
                
                response = requests.get(f"{prometheus_url}/api/v1/query", params={'query': q}, timeout=5)
                data = response.json()
                
                if not data['data']['result']:
                    print(f"[빈 결과 발생] {key} 쿼리에 데이터가 없습니다: {q}")
                    results[key] = 0.00
                else:
                    val = float(data['data']['result'][0]['value'][1])
                    results[key] = round(val, 2)
            except Exception as e:
                print(f"Query Error ({key}): {e}")
                results[key] = "Error"
        return results
    
    
    def get_cleanup_candidates(self, db_instance_ids):
        cleanup_list = []
        now = datetime.now(timezone.utc)
        
        # 모든 인스턴스 조회 (유령 자원 및 12시간 경과 체크)
        all_servers = list(self.conn.compute.servers(all_projects=True))
        
        for server in all_servers:
            raw_time = server.created_at
            
            # 오픈스택의 생성 시간 파싱 (보통 ISO 형식)
            # '2026-03-07T08:47:09Z' -> datetime 객체로 변환
            created_at = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
            is_old = (now - created_at) > timedelta(hours=1)
            is_orphaned = server.id not in db_instance_ids
            
            if is_old or is_orphaned:
                cleanup_list.append({
                    "type": "Instance",
                    "id": server.id,
                    "name": server.name,
                    "reason": "12시간 경과" if is_old else "유령 리소스(DB 미등록)",
                    "created_at": raw_time # 오픈스택 기준 시간
                })

        # 미사용 Floating IP 조회
        all_fips = list(self.conn.network.ips())
        for fip in all_fips:
            if not fip.port_id: # 연결된 장치가 없으면 낭비되는 자원
                cleanup_list.append({
                    "type": "Floating IP",
                    "id": fip.id,
                    "name": fip.floating_ip_address,
                    "reason": "미사용 IP (Unattached)",
                    "created_at": "N/A"
                })
                
        return cleanup_list