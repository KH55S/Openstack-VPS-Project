import openstack
import requests
import time
from openstack.connection import Connection
from datetime import datetime

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


    def get_instance_cpu_usage(self, prometheus_url, instance_ip):
        # 프로메테우스 API를 호출해 특정 인스턴스(IP)의 CPU 사용량 조회
        
        query = f'100 - (avg by (instance) (irate(node_cpu_seconds_total{{instance=~"{instance_ip}:.*", mode="idle"}}[1m])) * 100)'
        
        try:
            response = requests.get(f"{prometheus_url}/api/v1/query", params={'query': query}, timeout=2)
            result = response.json()
            
            if result['data']['result']:
                return round(float(result['data']['result'][0]['value'][1]), 2)
            return "No Data"
        except Exception as e:
            print(f"Monitoring Error : {e}")
        
    
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
                
                cpu_usage = self.get_instance_cpu_usage(prometheus_url, floating_ip)
                
                unified_data.append({
                    "instance_id": server.id,
                    "name": server.name,
                    "status": server.status,
                    "project_id": server.project_id,
                    "fixed_ip": fixed_ip,
                    "floating_ip": floating_ip,
                    "cpu": cpu_usage if cpu_usage is not None else "No Data",
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
        # 신규 유저를 위한 프로젝트/네트워크/서브넷/라우터 생성
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
            
            print(f"{username} 인프라 구축 완료 (Project: {project_id})")
            
            return {
                "project_id": project_id,
                "network_id": network_id,
                "project_name": project_name
            }
            
        except Exception as e:
            print(f"인프라 자동 구축 실패 : {e}")
            raise e
            

'''
# 인스턴스 생성 후 floating ip 할당 테스트
# create_vps_with_access 테스트
if __name__ == "__main__":
    manager = OpenStackManager()
    
    INSTANCE_NAME = "portfolio-vps-01"
    NETWORK_NAME = "shared_net" 
    IMAGE_NAME = "cirros" 
    FLAVOR_NAME = "m1.tiny"
    KEY_NAME = "khs-main-keypair"
    
    try:
        print(f"--- [테스트] {INSTANCE_NAME} 생성 시작 ---")
        result = manager.create_vps_with_access(
            INSTANCE_NAME, NETWORK_NAME, IMAGE_NAME, FLAVOR_NAME, KEY_NAME
        )
        print("--- [성공] 인스턴스 정보 ---")
        print(f"ID: {result['instance_id']}")
        print(f"Fixed IP: {result['fixed_ip']}")
        print(f"Floating IP: {result['floating_ip']}")
        
    except Exception as e:
        print(f"--- [실패] 에러 발생: {e} ---")
'''

'''
# 인프라 배포 -> 보안 설정 -> 모니터링 데이터 확보
if __name__ == "__main__":
    manager = OpenStackManager()
    PROM_URL = "http://192.168.35.100:9090"
    
    # 인스턴스 생성 및 보안 그룹 자동 적용 테스트
    print("Step 1: 인스턴스 및 보안 그룹 자동 배포 테스트")
    res = manager.create_vps_with_access(
        "sg-test-vps", "shared_net", "cirros", "m1.tiny", "khs-main-keypair"
    )
    print(f"생성 완료! Floating IP: {res['floating_ip']}")

    # 모니터링 데이터 연동 테스트 (인스턴스 부팅 시간을 위해 잠시 대기)
    print("\nStep 2: 실시간 모니터링 데이터 조회 테스트 (20초 대기...)")
    time.sleep(20)
    usage = manager.get_instance_cpu_usage(PROM_URL, res['floating_ip'])
    print(f"인스턴스({res['floating_ip']}) 현재 CPU 사용률: {usage}%")
'''

'''
# Packer로 빌드한 이미지로 인스턴스를 생성 후 모니터링 메트릭이 정상 수집되는지 확인
# 인스턴스 생성 - 보안 그룹 생성 및 연결 - 익스포터 활성화 대기했다가 모니터링
if __name__ == "__main__":
    manager = OpenStackManager()
    
    INSTANCE_NAME = "automated-monitoring-vps"
    NETWORK_NAME = "shared_net" 
    IMAGE_NAME = "ubuntu-22.04-monitoring-v1"
    FLAVOR_NAME = "m1.small"
    KEY_NAME = "khs-main-keypair"
    PROM_URL = "http://192.168.35.100:9090"

    try:
        print(f"--- [자동화 테스트] {INSTANCE_NAME} 배포 시작 ---")
        # 익스포터가 포함된 인스턴스 생성
        result = manager.create_vps_with_access(
            INSTANCE_NAME, NETWORK_NAME, IMAGE_NAME, FLAVOR_NAME, KEY_NAME
        )
        print(f"배포 성공! IP: {result['floating_ip']}")

        # 서비스 안정화 대기 (부팅 및 네트워크 활성화 시간)
        print("인스턴스 부팅 및 익스포터 활성화 대기 중 (40초)...")
        time.sleep(40)

        # 모니터링 데이터 수집 확인
        print(f"--- [모니터링 확인] {result['floating_ip']} 지표 조회 ---")
        usage = manager.get_instance_cpu_usage(PROM_URL, result['floating_ip'])
        print(f"현재 CPU 사용률: {usage}%")

    except Exception as e:
        print(f"--- [실패] {e} ---")
'''        


