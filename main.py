from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openstack_driver import OpenStackManager
from fastapi.responses import FileResponse
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cloud_portal.db")

app = FastAPI(title="KHS Private Cloud Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://hcloud.khs-server.cloud",
        "http://localhost:8000",    # 로컬 테스트용
        "http://localhost:8070",
        "http://192.168.35.100:8070"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = OpenStackManager()
PROM_URL = "http://192.168.35.100:9090"

@app.get("/")
async def read_index():
    return FileResponse('index.html')


@app.get("/api/users")
async def get_users():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        users = cursor.execute('SELECT username, project_name FROM users').fetchall()
        conn.close()
        return [dict(u) for u in users]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard")
async def get_dashboard():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        db_users = conn.execute('SELECT username, project_id, project_name FROM users').fetchall()
        conn.close()
        
        user_map = {u['project_id']: u['username'] for u in db_users}
        project_name_map = {u['project_id']: u['project_name'] for u in db_users}
        
        all_instances = manager.get_unified_dashboard_data(PROM_URL)
        
        for inst in all_instances:
            p_id = inst.get('project_id')
            inst['owner'] = user_map.get(p_id, "Unknown")
            inst['project_display_name'] = project_name_map.get(p_id, "Admin/Other")
            
        return all_instances
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/api/instances")
async def create_instance(name: str, username: str):
    # DB에서 유저의 오픈스택 컨텍스트 조회
    conn = sqlite3.connect('cloud_portal.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    user = cursor.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 사용자 입니다.")
    
    # 조회된 유저 고유의 network_id로 인스턴스 생성
    # network_id : OVS에서 특정 VNI로 캡슐화되는 기준
    try:
        result = manager.create_vps_with_access(
            instance_name=name,
            project_id=user['project_id'],
            network_id=user['network_id'],
            image_name="ubuntu-22.04-monitoring-v1", # 추후 여러 OS 선택 가능하도록 업데이트
            flavor_name="m1.small",
            key_name="khs-main-keypair"
        )
        return {"status": "success", "message": "Instance creation started", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.delete("/api/instances/destroy/{instance_id}")
async def delete_instance(instance_id: str):
    try:
        manager.delete_instance(instance_id)
        return {"status": "success", "message": "Instance deletion complete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))