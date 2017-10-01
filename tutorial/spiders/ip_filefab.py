import scrapy

class AuthorSpider(scrapy.Spider):
    name='ip_filefab'
    start_urls =['http://ip.filefab.com/index.php']

    # def start_requests(self):
    #     urls= ['http://ip.filefab.com/index.php']
        # for url in urls:
        #     yield scrapy.Request(url=url, meta = {
        #           'dont_redirect': True,
        #           'handle_httpstatus_list': [302]},
        #                      callback=self.parse)

    def parse(self, response):
        ip=response.xpath('.//*[@id="ipd"]/span/text()').extract_first()
        print(ip)
        return {ip:'hh'}
