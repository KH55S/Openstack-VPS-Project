#  HCloud Instance Access Guide
---

## 준비

- **등록된 이메일**: 관리자에게 제출한 인증용 이메일 주소
- **Cloudflare WARP**: 보안 터널 연결을 위한 전용 클라이언트 앱
- **SSH 클라이언트**: 터미널(Windows PowerShell, iTerm2, 등)

---

##  상세 접속 단계

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
3. 우측 상단 **`새 인스턴스 배포`** 버튼을 눌러 인스턴스를 생성합니다.
4. **`SSH Key (.pem)`** 버튼을 눌러 개인 키 파일을 다운로드합니다.
5. 인스턴스 리스트에서 본인 서버의 **Ext IP (192.168.35.xxx)** 주소를 복사합니다.

### 3단계: SSH 접속 실행
터미널을 실행하고 다운로드한 키 파일이 있는 경로에서 아래 명령어를 수행합니다.

```bash
# 기본 접속 명령어 (IP는 본인의 Ext IP로 변경)
ssh -i [본인_키_이름].pem ubuntu@192.168.35.xxx
```

## HCloud Infra 대시보드 구성
![메인 화면](https://img1.daumcdn.net/thumb/R1280x0.fjpg/?fname=http://t1.daumcdn.net/brunch/service/user/3fuW/image/sCtCeqMtmYJKDf7uLKA3EsaDhD8.jpg)
- 대시보드 접속 시 전체 프로젝트 내에서 생성된 모든 인스턴스가 표시되고, 세부정보는 아래와 같습니다.
  - 각 인스턴스의 기본 정보 : 프로젝트 / 인스턴스 이름 / 상태 / IP 주소 (내부/외부)
  - 모니터링 :  (내부/외부) / CPU, Memory, Disk I/O 사용량
  - 인스턴스 삭제
- 오픈스택 인프라를 보호하고 호스트 리소스의 절약을 위해 회수가 필요한 자원에 대한 정보가 표시되고, 회수 버튼을 눌러 리소스 회수를 진행할 수 있습니다.
  - 자원 회수 권고 기준은 아래와 같습니다.
    - 생성된 지 12시간이 지난 인스턴스
    - 할당되지 않은 Floating IP
    - 할당되지 않은 볼륨
---
![호스트 모니터링](https://img1.daumcdn.net/thumb/R1280x0.fjpg/?fname=http://t1.daumcdn.net/brunch/service/user/3fuW/image/sCtCeqMtmYJKDf7uLKA3EsaDhD8.jpg)
- 오픈스택 인프라가 구성된 호스트 서버의 모니터링 지표가 표시됩니다.

![프로젝트별 인스턴스 관리](https://img1.daumcdn.net/thumb/R1280x0.fjpg/?fname=http://t1.daumcdn.net/brunch/service/user/3fuW/image/sCtCeqMtmYJKDf7uLKA3EsaDhD8.jpg)
- 상단 View Project 필터를 통해 특정 프로젝트를 선택해 인스턴스 정보를 확인할 수 있습니다.