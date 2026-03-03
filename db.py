import sqlite3
from openstack_driver import OpenStackManager

def init_db():
    conn = sqlite3.connect('cloud_portal.db')
    cursor = conn.cursor()
    
    cursor.execute('''
       CREATE TABLE IF NOT EXISTS users (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           username TEXT UNIQUE,
           project_id TEXT,
           network_id TEXT,
           project_name TEXT
       ) 
    ''')
    
    conn.commit()
    conn.close()
    
    
#init_db()

# 사용자 등록 스크립트
def add_user(username, project_id, network_id, project_name):
    conn = sqlite3.connect('cloud_portal.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (username, project_id, network_id, project_name) VALUES (?, ?, ?, ?)',
                       (username, project_id, network_id, project_name))
        conn.commit()
        
        print(f"유저 {username} 등록 완료 (Network: {network_id})")
    except sqlite3.IntegrityError:
        print("이미 존재하는 유저입니다.")
    finally:
        conn.close()


# DB에 유저를 등록할 때 마다 프로젝트/네트워크/서브넷/라우터 구성을 수동으로 해야한다
# 유저 등록 시 프로젝트와 네트워크까지 등록되게 수정
#add_user("KHS_admin", "f3b4f0ad1ded48b48533c70d095055c6", "31b7198f-8093-449a-8ef9-f979f3a0fbca", "KHS_Project")



# DB 스키마 수정
def update_db_schema():
    conn = sqlite3.connect('cloud_portal.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            ALTER TABLE users ADD COLUMN key_name TEXT;
        ''')
        conn.commit()
    except sqlite3.OperationalError:
        print("이미 컬럼이 존재합니다.")
    finally:
        conn.close()
    
    
update_db_schema()