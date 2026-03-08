import os
import sqlite3
from openstack_driver import OpenStackManager

# 신규 유저(프로젝트) 등록
def register_new_user(username):
    manager = OpenStackManager()
    conn = sqlite3.connect('cloud_portal.db')
    
    try:
        infra = manager.setup_tenant_infrastructure(username)
        
        key_dir = "./user_keys"
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, f"{infra['key_name']}.pem")
        
        with open(key_path, "w") as f:
            f.write(infra['private_key'])
        os.chmod(key_path, 0o600)
        
        
        cursor = conn.cursor()        
        cursor.execute('''
            INSERT INTO users (username, project_id, network_id, project_name, key_name)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, infra['project_id'], infra['network_id'], infra['project_name'], infra['key_name']))
        
        conn.commit()
        
        print(f"{username} 유저 및 인프라 등록 완료")
        print(f"Key saved to : {key_path}")
        
    except Exception as e:
        print(f"유저 등록 실패 : {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    register_new_user("InfraTeam_VDI")