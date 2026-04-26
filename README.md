# narajangteo-pro

나라장터 공공조달 API 6종을 통합한 MCP 서버입니다. Claude Desktop 등 MCP 클라이언트와 연결해 자연어로 입찰공고 검색, 시장 분석, 입찰 적합도 평가 등을 수행할 수 있습니다.

---

## 주요 기능

### 공공조달 API 6종 연동

나라장터 주요 공공 API를 통합해 다양한 데이터를 조회할 수 있도록 구성했습니다.

- **입찰공고**: 키워드, 기관, 기간 기준 공고 검색
- **낙찰정보**: 낙찰 업체 및 금액 조회
- **계약정보**: 실제 계약 체결 내역 확인
- **계약과정통합공개**: 사전규격부터 계약까지 전체 진행 과정 추적
- **조달요청**: 발주 이전 단계 데이터 조회
- **종합쇼핑몰 품목**: 단가계약 등록 품목 검색

공통 API 클라이언트(`api/client.py`)에서 다음 기능을 처리합니다.

- 응답 형식 정규화
- 요청 타임아웃 시 자동 재시도 (최대 2회)
- 메모리 캐시 (기본 5분)

---

### MCP 도구 8종 구성

LLM 환경에서 효율적으로 활용할 수 있도록 기능 단위 도구로 구성했습니다.

| 도구명 | 설명 |
|--------|------|
| `search_procurement` | 입찰 / 낙찰 / 계약 / 요청 / 쇼핑몰 통합 검색 |
| `get_procurement_detail` | 상세 정보 조회 |
| `trace_procurement_lifecycle` | 조달 진행 단계 추적 |
| `analyze_market` | 키워드 기반 시장 동향 분석 |
| `analyze_competitor` | 특정 기업 조달 활동 분석 |
| `score_bid_fit` | 기업 정보 기반 입찰 적합도 분석 |
| `manage_watchlist` | 관심 키워드 등록 및 신규 공고 확인 |
| `manage_company_profile` | 회사 프로필 저장 / 불러오기 |

---

### 자연어 입력 처리

사용자가 일상적인 표현으로 입력해도 API 파라미터로 자동 변환되도록 구현했습니다.

**기간 표현** — `최근 7일` / `지난 3개월` / `올해`

**금액 표현** — `5억` / `1.5억` / `3천만원`

**업무구분 동의어** — `서비스 → 용역` / `건설 → 공사`

---

### 상태 저장

SQLite 기반으로 사용자 설정 데이터를 저장합니다. 저장 항목은 Watchlist와 회사 프로필이며, 기본 저장 위치는 아래와 같습니다.

```
~/.narajangteo-pro/state.db
```

---

## 빠른 시작

### 1. API 키 발급

[공공데이터포털](https://www.data.go.kr)에서 아래 서비스를 활용신청한 후, 마이페이지 → 개발계정에서 **ServiceKey의 Decoding 값**을 복사합니다.

- 조달청_나라장터 입찰공고정보서비스
- 조달청_나라장터 낙찰정보서비스
- 조달청_나라장터 계약정보서비스
- 조달청_나라장터 계약과정통합공개서비스

### 2. 설치

```bash
# uvx (권장 — Python 설치 없이 실행)
uvx narajangteo-pro

# npx
npx narajangteo-pro

# pip
pip install narajangteo-pro
narajangteo-pro
```

### 3. Claude Desktop 연결

아래 경로의 설정 파일을 수정합니다.

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "narajangteo-pro": {
      "command": "uvx",
      "args": ["narajangteo-pro@latest"],
      "env": {
        "NARA_API_KEY": "발급받은_디코딩_서비스키"
      }
    }
  }
}
```

Claude Desktop을 재시작하면 바로 사용할 수 있습니다.

> "최근 1개월 AI 챗봇 분야 시장 분석해줘"
>
> "공고번호 20260415123 사전규격부터 계약까지 전체 진행상황 보여줘"
>
> "우리 회사 프로필로 이 공고 입찰해도 될지 평가해줘"

---

## 아키텍처

```
┌─────────────────────────────────────┐
│  Claude Desktop / Cursor / VS Code  │
└──────────────────┬──────────────────┘
                   │ MCP (stdio | HTTP)
┌──────────────────▼──────────────────┐
│          narajangteo-pro            │
│  ┌────────┐  ┌──────────┐  ┌──────┐ │
│  │ Tools  │→ │Analytics │→ │ DB   │ │
│  └───┬────┘  └────┬─────┘  └──────┘ │
│      └────────────┘                 │
│         ┌──────────┐                │
│         │API Client│                │
│         └────┬─────┘                │
└──────────────┼──────────────────────┘
               │
      ┌─────────▼──────────┐
      │   공공데이터포털    │
      │  나라장터 API 6종   │
      └────────────────────┘
```

---

## 라이선스

MIT
