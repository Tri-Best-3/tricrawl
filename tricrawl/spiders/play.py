import scrapy
import re
from datetime import datetime, timezone
from tricrawl.items import LeakItem


class PlaySpider(scrapy.Spider):
    """
    Play 랜섬웨어 그룹 크롤러 (Play News)
    
    Lineage:
    - 수집 대상: Play 랜섬웨어 그룹의 피해자 목록
    - 구조: 테이블 기반, th.News 가 하나의 피해자 카드
    - site_type: "Ransomware"
    """
    
    name = "play"
    allowed_domains = ["mbrlkbtq5jonaqkurjwmxftytyn2ethqvbxfu4rgjbkkknndqwae6byd.onion"]
    start_urls = [
        "http://mbrlkbtq5jonaqkurjwmxftytyn2ethqvbxfu4rgjbkkknndqwae6byd.onion/"
    ]
    
    # Tor 미들웨어 필수 설정
    custom_settings = {
        "DOWNLOADER_MIDDLEWARES": {
            "tricrawl.middlewares.darknet_requests.RequestsDownloaderMiddleware": 543,
            "tricrawl.middlewares.TorProxyMiddleware": None,
            "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": None,
        },
        "DOWNLOAD_DELAY": 3,
        "CLOSESPIDER_PAGECOUNT": 3,  # 테스트용 제한
    }

    def parse(self, response):
        """
        Main Parser: th.News 블록을 순회하며 피해자 데이터 추출
        """
        self.logger.info(f"[Play] Status: {response.status}, URL: {response.url}")
        
        # Play News는 th.News 클래스가 각 피해자 카드
        posts = response.css('th.News')
        
        for post in posts:
            # 1. 피해자 이름 추출 (첫 번째 텍스트 노드)
            # th 태그의 직접 텍스트만 가져옴 (div 내부 제외)
            all_text = post.xpath('text()').getall()
            title = ""
            for t in all_text:
                t = t.strip()
                if t:
                    title = t
                    break
            
            if not title:
                continue
            
            # 2. onclick에서 topic ID 추출
            onclick = post.attrib.get('onclick', '')
            topic_match = re.search(r"viewtopic\('([^']+)'\)", onclick)
            topic_id = topic_match.group(1) if topic_match else ""
            url = f"http://mbrlkbtq5jonaqkurjwmxftytyn2ethqvbxfu4rgjbkkknndqwae6byd.onion/topic.php?id={topic_id}" if topic_id else response.url
            
            # 3. 내부 div에서 정보 추출
            divs = post.css('div::text').getall()
            location = ""
            website = ""
            added_date = ""
            pub_date = ""
            status = ""
            
            for div_text in divs:
                div_text = div_text.strip()
                if not div_text:
                    continue
                # 국가 (location 아이콘 뒤)
                if div_text and not location and not div_text.startswith(('www.', 'views:', 'added:', 'publication')):
                    if 'PUBLISHED' not in div_text and 'DAY' not in div_text:
                        location = div_text
                # 웹사이트
                if div_text.startswith('www.'):
                    website = div_text
                # 날짜
                if div_text.startswith('added:'):
                    added_date = div_text.replace('added:', '').strip()
                if div_text.startswith('publication date:'):
                    pub_date = div_text.replace('publication date:', '').strip()
                # 상태
                if 'PUBLISHED' in div_text or 'DAY' in div_text:
                    status = div_text
            
            # 4. 본문 구성
            content_parts = []
            if location:
                content_parts.append(f"Location: {location}")
            if website:
                content_parts.append(f"Website: {website}")
            if added_date:
                content_parts.append(f"Added: {added_date}")
            if pub_date:
                content_parts.append(f"Publication: {pub_date}")
            if status:
                content_parts.append(f"Status: {status}")
            
            content = "\n".join(content_parts)
            
            yield LeakItem(
                source="Play Ransomware",
                title=title,
                url=url,
                author="Play Group",
                timestamp=datetime.now(timezone.utc).isoformat(),
                content=content,
                category="Ransomware",
                site_type="Ransomware",  # ⭐ 필수 필드
                dedup_id=None
            )
