# ☁️ HCloud: Kolla-Ansible 기반 프라이빗 클라우드 자동화 플랫폼

**`HCloud`**(HS-Cloud)는 서비스 개발 목적이 아닌, **오픈스택(OpenStack)의 내부 작동 원리 파악**과 **인프라 자동화 역량 확보**를 위해 구축된 개인형 프라이빗 클라우드 포털입니다. 노트북이라는 제한된 리소스 환경에서 **Kolla-Ansible**을 통해 컨테이너 기반 인프라를 배포하고, 인스턴스의 생명주기(Provisioning-Configuration-Cleanup)를 소프트웨어적으로 자동화하여 운영 효율성을 극대화했습니다.

---

##  프로젝트 목적
1. **오픈스택 아키텍처 심층 이해**: Kolla-Ansible을 이용한 컨테이너 기반 오픈스택 배포 및 서비스(Nova, Neutron, Keystone 등) 간 상호작용 분석.
2. **Infrastructure as Code (IaC)**: 인스턴스 생성 후 수동 개입 없는 SSH 접속 환경 및 초기 OS 환경 설정 자동화(Ansible 연동)
3. **가용 자원 최적화**: 노트북의 한정된 리소스 보호를 위해 유휴 자원 및 DB-인프라 불일치 자원을 탐지 및 회수
4. **관측성(Observability) 확보**: Prometheus 데이터를 활용한 물리 호스트 및 가상 인스턴스의 실시간 성능 지표 시각화

---

## Tech Stack
* **Cloud Infrastructure**: OpenStack, Kolla-Ansible, Cloudflare Zero Trust
* **Automation**: Ansible (Dynamic Inventory), OpenStack SDK
* **Backend**: FastAPI (Python 3.10), SQLite
* **Monitoring**: Prometheus, Node Exporter, Chart.js
* **DevOps**: Docker, Docker Compose

---

## 핵심 자동화 로직

본 프로젝트의 '자동화 로직'은 단순히 스크립트를 실행하는 것이 아니라, **이벤트 발생 → 상태 감지 → 정책 기반 실행**의 흐름을 가집니다.

### 1. 전용 테넌트 인프라 자동 구축
* 유저(프로젝트) 등록 시 OpenStack SDK를 통해 격리된 프로젝트, 네트워크, 서브넷, 라우터, 키페어 생성 및 라우터에 외부 게이트웨이와 내부 인터페이스를 연결합니다. (인스턴스 내에서 인터넷 사용 가능)

### 2. Ansible 기반 인프라 구성 자동화 (Event-Driven)
* 인스턴스 생성 후 FastAPI가 백그라운드에서 동적 인벤토리(Dynamic Inventory)를 생성하고 앤서블 플레이북을 트리거합니다.
* 앤서블이 생성된 인스턴스 내에서 패키지 업데이트 및 호스트네임 동기화를 자동으로 수행합니다. 

### 3. 호스트 자원 최적화 및 회수
* 매 주기마다 DB 기록과 실제 오픈스택 자원 상태를 교차 검증하여 유휴 리소스를 감지하고, 생성 후 12시간이 경과된 인스턴스를 분류합니다.
* 노트북이라는 한정된 호스트 서버의 리소스 고갈을 방지하고 오픈스택 인프라를 보호하기 위해 운영 자동화 프로세스를 구축했습니다.
---

## 인스턴스 상세 접속 단계

### 1단계 : Cloudflare WARP 설정 (VPN 연결)
인스턴스 연결을 위해 **Cloudflare Zero Trust** 보안 터널을 사용합니다.

1. [Cloudflare WARP 공식 홈페이지](https://1.1.1.1/)에서 OS에 맞는 클라이언트를 설치합니다.
2. **로그인 방식 변경**:
    * WARP 앱 실행 → **톱니바퀴** → **기본 설정** → **계정** → **Cloudflare Zero Trust로 로그인**를 클릭합니다.
    * 팀 이름에 `Test`를 입력합니다.
3. **이메일 인증**:
    * 브라우저가 열리면 등록된 이메일을 입력합니다.
    * 해당 이메일로 발송된 6자리 인증번호(PIN)를 입력합니다.
4. **연결 확인**: 앱 스위치를 켰을 때 버튼이 파란색(Connected)으로 표시되면 터널 연결 성공입니다.

### 2단계: SSH 키 및 접속 IP 확보
1. [HCloud 포털](Test)에 접속합니다.
2. 상단 **View Project** 필터에서 본인의 유저명을 선택합니다.
3. 우측 상단 **`새 인스턴스 배포`** 버튼을 눌러 인스턴스 배포를 시작합니다.
4. **`SSH Key (.pem)`** 버튼을 눌러 개인 키 파일을 다운로드합니다.
5. 인스턴스 리스트에서 본인 서버의 **Ext IP (192.168.35.xxx)** 주소를 확인합니다.

### 3단계: SSH 접속 실행
터미널을 실행하고 다운로드한 키 파일이 있는 경로에서 아래 명령어를 수행합니다.

```bash
# 기본 접속 명령어 (IP는 본인의 Ext IP로 변경)
ssh -i [본인_키_이름].pem ubuntu@192.168.35.xxx
```
---

## 대시보드 구성 및 모니터링

### 1. 메인 대시보드 (인스턴스 관리)
<img width="1298" alt="메인 대시보드 화면" src="https://github.com/user-attachments/assets/7c63010a-6ad3-4663-99d4-80809d0a6508" />

* **인스턴스 매니페스트** : 프로젝트별 소유자, 인스턴스 이름, 상태, 내부/외부 IP 및 실시간 CPU/MEM/Disk I/O 지표를 제공합니다.
* **모니터링 지표 동기화** : **Prometheus**와 연동하여 개별 인스턴스의 모니터링 지표를 최신 상태로 유지합니다.
---

### 2. 자원 회수 권고
<img width="1207" height="642" alt="스크린샷 2026-03-08 191214" src="https://github.com/user-attachments/assets/c13dab0b-f825-43dc-bf73-8089568e2476" />

* **리소스 가용성 관리** : 노트북의 물리 자원 고갈을 방지하기 위해 생성 인스턴스(12시간 경과 / DB 미등록) 및 미사용 Floating IP를 자동으로 필터링합니다.
* **회수 기능** : 회수 버튼을 눌러 오픈스택 자원을 삭제합니다.
---
### 3. 멀티 테넌트 뷰 (멀티 테넌트 필터)
<img width="1199" alt="멀티 테넌트 뷰" src="https://github.com/user-attachments/assets/8c7536db-c330-4fdd-b9d6-cfb4c5f9a753" />

* 특정 프로젝트(사용자)별 인스턴스 현황을 조회할 수 있습니다.
* 다중 사용자 환경에서 각 테넌트의 인프라 상태를 독립적으로 관리 및 모니터링할 수 있습니다.
---

### 4. 호스트 서버 모니터링
<img width="1197" alt="호스트 서버 모니터링" src="https://github.com/user-attachments/assets/c5dfc43d-e7f8-4663-bebb-257b33cc7ad5" />

* 오픈스택 인프라가 구동되는 물리 호스트의 OS Load, 전체 자원 점유율을 모니터링하여 인프라 안정성을 유지합니다.

---

