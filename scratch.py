import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

async def test():
    conf = BrowserConfig(headless=True, text_mode=True)
    run_conf = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=30000)
    async with AsyncWebCrawler(config=conf) as crawler:
        print("Testing przychodniakul.pl...")
        res = await crawler.arun(url="https://przychodniakul.pl", config=run_conf)
        print("Success:", res.success)
        if hasattr(res, 'error_message'): print("Error:", res.error_message)
        
        print("Testing hipoteczna4.lublin.pl...")
        res2 = await crawler.arun(url="https://hipoteczna4.lublin.pl", config=run_conf)
        print("Success:", res2.success)
        if hasattr(res2, 'error_message'): print("Error:", res2.error_message)

asyncio.run(test())
