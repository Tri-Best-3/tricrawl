"""
Best Carding World Forum Spider
Target: http://bestteermb42clir6ux7xm76d4jjodh3fpahjqgbddbmfrgp4skg2wqd.onion/
Type: phpBB Forum (sid=... , a.topictitle, li.row, dd.lastpost, ...)
"""
import scrapy
import structlog
import yaml
from pathlib import Path
from tricrawl.items import LeakItem
from datetime import datetime, timedelta, timezone
# import hashlib
import re

logger = structlog.get_logger(__name__)

RX_LASTPOST_DT = re.compile(r"\b[A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[ap]m\b")
RX_FORUM_DT = re.compile(
    r"\b[A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[ap]m\b"
)


class BestCardingWorldSpider(scrapy.Spider):
    """
    BestCardingWorld 포럼 크롤러 (XenForo).

    데이터 컨트랙트:
    - LeakItem의 필수 필드(source/title/url/author/timestamp)를 반드시 채움
    - content는 요약/클린 텍스트로 구성 (키워드 필터 입력)
    - category는 가능하면 게시판/분류명으로 채움
    """
    
    name = "best_carding_world"
    
    # 동적 URL 생성 (Config 로드 후 __init__에서 설정)
    start_urls = []
    
    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        'DOWNLOAD_TIMEOUT': 120,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0',
        'COOKIES_ENABLED': True,
        # DarkNet 전용 미들웨어 사용
        'DOWNLOADER_MIDDLEWARES': {
            'tricrawl.middlewares.darknet_requests.RequestsDownloaderMiddleware': 543,
            'tricrawl.middlewares.TorProxyMiddleware': None,
            'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': None,
        }
    }
    
    def __init__(self, *args, **kwargs):
        """YAML 설정을 로드하고 start_urls/board limits를 구성한다."""
        super(BestCardingWorldSpider, self).__init__(*args, **kwargs)
        
        # 설정 파일 로드
        self.config = {}
        try:
            # 프로젝트 루트 (tricrawl/spiders -> ../../)
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / "config" / "crawler_config.yaml"
            
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
                logger.info(f"Config loaded from {config_path}")
            else:
                logger.warning("Config file not found, using defaults")
                
        except Exception as e:
            logger.error(f"Config load failed: {e}")
            
        # 전역 설정 적용
        global_conf = self.config.get('global', {})
        self.days_limit = global_conf.get('days_to_crawl', 3)
        override_days = kwargs.get("days_limit")
        if override_days is not None:
            try:
                self.days_limit = int(override_days)
            except ValueError:
                logger.warning("Invalid days_limit override", value=override_days)
        
        # 스파이더별 설정 로드 및 start_urls 구성
        spider_conf = self.config.get('spiders', {}).get('best_carding_world', {})
        self.target_url = spider_conf.get('target_url')
        self.endpoints = spider_conf.get('endpoints', {})
        self.board_limits = spider_conf.get('boards', {})
        
        if self.target_url and self.endpoints:
            # Base URL의 trailing slash 처리
            base = self.target_url.rstrip('/')
            for key, path in self.endpoints.items():
                # Endpoints path의 leading slash 처리
                clean_path = path.lstrip('/')
                full_url = f"{base}/{clean_path}"
                self.start_urls.append(full_url)
                logger.debug(f"Added start URL: {full_url} (Key: {key})")
        else:
            logger.error("Target URL or Endpoints NOT found in config. Spider may not crawl anything.")

        # 기본값 로직 조정: Config에 없으면 내부 기본값(5) 사용
        self.default_max_pages = 5
        
        logger.info(f"Loaded Config - Global Days: {self.days_limit}, URLs: {len(self.start_urls)}")


    # def get_max_pages_for_url(self, url):
    #     """URL에 해당하는 게시판별 제한 확인 (config의 boards 기준)."""
    #     # Config의 Endpoints 경로를 역추적하여 Key를 찾고, 그 Key로 Limits를 조회
    #     # 현재는 URL에 endpoint path가 포함되어 있는지 단순 문자열 매칭으로 확인
    #     for key, path in self.endpoints.items():
    #         # URL 디코딩 문제가 있을 수 있으므로 단순 포함 여부 확인이 안전
    #         # Config의 path 부분만 잘라서 비교
    #         if path.lstrip('/') in url:
    #             return self.board_limits.get(key, self.default_max_pages)
        
    #     return self.default_max_pages


    # [작성 시간 추출]
    # lastpost 형식 내부 시간을 기준으로 함
    def extract_lastpost_dt_text(self, row):
        lastpost_text = " ".join(row.css("dd.lastpost *::text").getall()).strip()
        m = RX_FORUM_DT.search(lastpost_text)
        return m.group(0) if m else ""
    
    # datetime 형식으로 변경
    def parse_forum_dt(self, dt_str: str):
        if not dt_str:
            return None
        try:
            # Sun Jan 18, 2026 11:36 am
            dt = datetime.strptime(dt_str, "%a %b %d, %Y %I:%M %p")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # 게시글 제목 기준 파싱
    def parse(self, response):
        # # 현재 페이지 카운트 (기본 1)
        # page_count = response.meta.get('page_count', 1)
        # # 현재 게시판의 Max Pages 결정
        # current_max_pages = self.get_max_pages_for_url(response.url)

        logger.info(f"BestCardingWorld 메인 페이지 접근: {response.url}")
        # logger.info(f"BestCardingWorld 접속 (Page {page_count}/{current_max_pages})", url=response.url)
        
        self.logger.info("status=%s url=%s", response.status, response.url)

        for row in response.css("li.row"):
            title = row.css("a.topictitle::text").get()
            href  = row.css("a.topictitle::attr(href)").get()

            if not title or not href:
                continue

            url = response.urljoin(href)
            
            # lastpost_text = " ".join(row.css("dd.lastpost *::text").getall()).strip()
            author = row.css("dd.lastpost a.username-coloured::text").get() or "Unknown"

            dt_text = self.extract_lastpost_dt_text(row)
            dt = self.parse_forum_dt(dt_text)
            ts_iso = dt.isoformat() if dt else datetime.now(timezone.utc).isoformat()
            

            item = LeakItem()
            item["source"] = "BestCardingWorld"
            item["title"] = title.strip()
            item["url"] = url
            item["author"] = author.strip()
            # item["timestamp"] = datetime.now(timezone.utc).isoformat()  # 일단 수집 시각 
            item["timestamp"] = ts_iso
            item["content"] = ""
            item["category"] = "data_breach"

            # yield item

            yield scrapy.Request(
                url=url,
                callback=self.parse_topic,
                cb_kwargs={"item": item},
                dont_filter=True,  # 같은 URL이더라도 항상 확인하고 싶으면 True
            )
        

    # 게시글 상세 페이지 파싱
    def parse_topic(self, response, item: LeakItem):
        # phpBB 계열 (div.postbody)
        # post = (
        #     response.css("div.postbody").getall()
        # )

        # # postbody가 여러 개면 첫 번째를 기준으로 본문 추출
        # first_post = response.css("div.postbody").get()
        # if not first_post:
        #     # fallback: phpBB 변형들
        #     first_post = response.css("div.post div.content").get()

        # 우선순위: div.postbody .content → div.postbody 전체
        text_parts = response.css("div.postbody .content *::text").getall()
        if not text_parts:
            text_parts = response.css("div.postbody *::text").getall()

        tmp = " ".join(text_parts)
        content = " ".join((tmp or "").split())

        # 길이 제한
        MAX_CONTENT_LEN = 2000
        if len(content) > MAX_CONTENT_LEN:
            content = content[:MAX_CONTENT_LEN] + " ..."

        item["content"] = content

        yield item
