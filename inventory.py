#!/usr/bin/env python3
import json
import sqlite3
import os
from openstack_driver import OpenStackManager


def get_inventory():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, "cloud_portal.db")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    db_instances = cursor.execute("SELECT instance_id, username, instance_name FROM instances").fetchall()
    conn.close()
    
    manager = OpenStackManager()
    
    inventory = {
        '_meta': {'hostvars': {}},
        'all': {'children': ['openstack_nodes']},
        'openstack_nodes': {'hosts': []}
    }
    
    for row in db_instances:
        try:
            # 오픈스택 API로 인스턴스 조회
            servers = list(manager.conn.compute.servers(
                all_projects=True,
                uuid=row['instance_id']
            ))
            server = servers[0]
            
            # Floating IP 찾기
            floating_ip = "N/A"
            for net_name, addr_list in server.addresses.items():
                for addr in addr_list:
                    if addr.get("OS-EXT-IPS:type") == "floating":
                        floating_ip = addr['addr']
                        
            if floating_ip == "N/A": continue
            
            # 앤서블로 호스트 정보 구성
            hostname = row['instance_name']
            inventory['openstack_nodes']['hosts'].append(hostname)
            inventory['_meta']['hostvars'][hostname] = {
                'ansible_host': floating_ip,
                'ansible_user': 'ubuntu',
                'ansible_ssh_private_key_file': f"./user_keys/{row['username']}_key.pem",
                'ansible_ssh_common_args': '-o StrictHostKeyChecking=no',
                'target_hostname': row['instance_name']
            }
        except Exception as e:
            import sys
            print(f"Error processing {row['instance_id']}: {e}", file=sys.stderr)
            continue
    return inventory

if __name__ == "__main__":
    print(json.dumps(get_inventory()))