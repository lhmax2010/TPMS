# TPMS Performance Database

TPMS 성능 테스트 결과를 SQLite DB에 저장하고 조회/분석하는 도구입니다.

## 파일 구성

| 파일 | 설명 |
|------|------|
| `tpms_db.py` | DB 관리 CLI (import, save, query, delete, verify, backup) |
| `tpms_web.py` | 정적 HTML 리포트 생성기 (Chart.js 기반 트렌드 차트) |
| `test_sample.xml` | 테스트용 샘플 XML |

## 빠른 시작

### 1. 단일 XML 파일 저장

```bash
python3 tpms_db.py --save perfpublisher.xml --job 10.0-unified-rpi-32bit --build 1 --db tpms.db
```

### 2. Jenkins 전체 빌드 일괄 import

```bash
python3 tpms_db.py --import-jenkins /var/lib/jenkins/jobs --db tpms.db
```

### 3. 최근 트렌드 조회

```bash
python3 tpms_db.py --latest 10.0-unified-rpi-32bit --metric BootingTime --count 30 --db tpms.db
```

### 4. 프로파일 간 비교

```bash
python3 tpms_db.py --compare "9.0-unified-rpi-32bit,10.0-unified-rpi-32bit" --metric BootingTime --db tpms.db
```

### 5. 버전별 비교

```bash
python3 tpms_db.py --range "8.0,9.0,10.0" --profile-pattern unified-rpi --metric BootingTime --db tpms.db
```

### 6. 통계 및 검증

```bash
python3 tpms_db.py --stats --db tpms.db
python3 tpms_db.py --verify --db tpms.db
python3 tpms_db.py --benchmark --db tpms.db
```

### 7. 데이터 삭제

```bash
# dry-run으로 확인
python3 tpms_db.py --delete --job 10.0-unified-rpi-32bit --build 5 --dry-run --db tpms.db

# 실제 삭제
python3 tpms_db.py --delete --job 10.0-unified-rpi-32bit --build 5 --force --db tpms.db
```

### 8. 백업 및 복원

```bash
# 백업
python3 tpms_db.py --export tpms.db --output tpms_backup.sql

# 복원
python3 tpms_db.py --import-sql tpms_backup.sql --db tpms_restored.db
```

### 9. 웹 리포트 생성

```bash
python3 tpms_web.py --db tpms.db --output /var/www/tpms_report
```

생성된 `index.html`을 브라우저로 열면 대시보드, 프로파일별 트렌드 차트, 메트릭별 비교 페이지를 확인할 수 있습니다.

## DB 스키마

```sql
CREATE TABLE performance_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,          -- 프로파일명 (예: 10.0-unified-rpi-32bit)
    build_number INTEGER,            -- 빌드 번호
    build_id TEXT,                   -- 빌드 ID (예: tizen-10.0-unified_20260716.015122)
    test_time TEXT,                  -- 테스트 시간
    test_name TEXT NOT NULL,         -- 테스트명 (예: Booting Time)
    metric_name TEXT,                -- 메트릭명 (예: BootingTime)
    metric_value REAL,               -- 측정값
    metric_unit TEXT,                -- 단위 (s, MB, KB, ms)
    is_relevant INTEGER DEFAULT 0,   -- 핵심 메트릭 여부
    executed INTEGER DEFAULT 1,      -- 실행 여부
    passed INTEGER DEFAULT 1,        -- 성공 여부
    has_timed_out INTEGER DEFAULT 0, -- 타임아웃 여부
    source_file TEXT,                -- 원본 XML 파일 경로
    imported_at TEXT DEFAULT (datetime('now','localtime'))
);

-- 중복 방지 인덱스
CREATE UNIQUE INDEX idx_unique ON performance_data(job_name, build_number, test_name, metric_name);

-- 조회 성능 인덱스
CREATE INDEX idx_job_metric ON performance_data(job_name, metric_name, build_number);
```

## 주요 메트릭

| 메트릭 | 단위 | 설명 |
|--------|------|------|
| BootingTime | s | 부팅 시간 |
| IdleMemoryUsage | MB | Idle 상태 메모리 사용량 |
| NANDUsage | MB | NAND 사용량 |
| AppLaunchingTime | s | 앱 런칭 시간 |
| WebAppLaunchingTime | s | 웹 앱 런칭 시간 |

## Jenkins 연동

Jenkins pipeline의 post-build step에서 다음과 같이 호출:

```groovy
post {
    always {
        sh '''
            cd $WORKSPACE/db
            python3 tpms_db.py --save ../standalone/workspace/perfpublisher.xml \
                --job ${JOB_NAME} --build ${BUILD_NUMBER} --replace --db tpms.db
            python3 tpms_web.py --db tpms.db --output /var/www/tpms_report
        '''
    }
}
```
