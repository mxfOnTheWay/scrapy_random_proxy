import logging
import threading
import threadpool
import requests
import re
import random
import os
import json
import time

from bs4 import BeautifulSoup
from twisted.internet import defer
from twisted.internet.error import TimeoutError, ConnectionRefusedError, \
    ConnectError, ConnectionLost, TCPTimedOutError, ConnectionDone

logger=logging.getLogger(__name__)

class ProxyMiddleware(object):
    DONT_RETRY_ERRORS = (
    defer.TimeoutError, TimeoutError, ConnectionRefusedError, ConnectError, ConnectionLost, TCPTimedOutError,
    ConnectionDone)

    def __init__(self,*args,**kwargs):
        self.proxies=set()
        self.proxy_chosen=''
        #self.event=threading.Event()
        #self.ban_code=[503, ]
        #判断有没有存储的代理文件，若有，则从中读取；否则将代理ip集合设为空
        if os.path.exists('proxy_used_file') and os.path.getsize('proxy_used_file')>0:
            with open('proxy_used_file', 'r') as f:
                proxy_store = json.load(f)
                self.proxies_used = set(proxy_store)
        else:
            self.proxies_used=set()

            self.fetch_new_proxies()

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        return cls(crawler.settings)

    def fetch_new_proxies(self):
        """
        获取新的代理，从多个网站上获取代理，每个网站开启一个线程
        """
        logger.info('Starting fetch new proxies.')
        urls = ['xici', '89ip']
        threads=[]
        for url in urls:
            t=ProxyFetch(self.proxies,url)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()
        #调用proxies_test方法，对代理进行检验，将可用的添加到可用代理集合。
        #处理方法为proxy_deal_first，即对刚刚获取到ip列表进行检测的方法
        self.proxies_test(self.proxies,self.proxy_deal_first)
        #print(self.proxies_used)
        #将获取到的可用代理存储
        self.proxies_store(self.proxies_used)
        #将初始代理列表情况
        self.proxies=set()


    def proxy_check(self,proxy):
        '''
        检查单一代理是否可用，若访问成功，返回True，否则为False
        时间间隔默认设置成5s
        '''
        url='http://www.ifeng.com'
        proxies={'http':proxy}
        try:
            r = requests.get(url, proxies=proxies, timeout=5, allow_redirects=False)
            #print(r.status_code)
            if r.status_code == 200:
                print('proxy check  ok !!!!!!')
                return True
            else:
                print('proxy check  false !!!!!! no exception')
                return False
        except:
            print('proxy check  false !!!!!!')
            return False

    def proxy_deal_first(self,proxy):
        '''
        初始ip处理程序：网上下载代理后，调用代理检测方法。若可用（返回True），则添加到可用代理中
        '''
        if self.proxy_check(proxy):
            self.proxies_used.add(proxy)
            print('add:',proxy)

    def proxies_test(self,proxies,proxies_deal_function):
        '''
        通过线程池调用测试代理方法，每次10个线程
        :param proxies: 为要检测的代理列表
        :param proxies_deal_function: 为检测的方法
        :return: 
        '''
        #调用线程池，每次10个线程
        pool=threadpool.ThreadPool(10)
        # 调用makeRequests创建了要开启多线程的函数
        requests = threadpool.makeRequests(proxies_deal_function,proxies)
        # 所有要运行多线程的请求扔进线程池
        [pool.putRequest(req) for req in requests]
        #等待所有的线程完成工作后退出
        pool.wait()

    def proxy_deal_used(self,proxy):
        '''
        在使用过程中，检测可用代理，若不可以，从可用代理中删除
        '''
        print('used proxy check @-used',proxy)
        if self.proxy_check(proxy)==False:
            self.proxies_used.remove(proxy)
            print(proxy,"removed")
        else:
            return True

    def proxies_store(self,proxies):
        '''
        存储代理
        当之前已经存在此文件时，先删除再存储
        '''
        if os.path.exists('proxy_used_file'):
            os.remove('proxy_used_file')

        with open('proxy_used_file','w') as f:
            json.dump(list(proxies),f)

    def process_request(self, request, spider):
        '''
        设置代理   
        '''
        self.proxy_chose()
        logger.info('proxy_used:%s '%self.proxy_chosen)
        request.meta['dont_redirect'] = True
        request.meta['proxy']=self.proxy_chosen


    def proxy_chose(self):
        '''
        当代理列表中有代理时，从中随机选择代理，选择后，先进行检测。若检测成功，返回true；
        若无代理，则去获取新代理
        '''
        while True:
            if len(self.proxies_used)>0:
                self.proxy_chosen = random.choice(list(self.proxies_used))
                if self.proxy_deal_used(self.proxy_chosen):
                    break
            else:
                print('no new proxy@@@@')
                self.fetch_new_proxies()

    def process_response(self, request, response, spider):
        """
        检查response.status, 若返回不是成功（200），则切换代理，重新请求
        
        """
        if "proxy" in request.meta.keys():
            logger.debug("%s %s %s" % (request.meta["proxy"], response.status, request.url))
        else:
            logger.debug("None %s %s" % (response.status, request.url))

        self.proxies_store(self.proxies_used)

        # status不是正常的200而且不在spider声明的正常爬取过程中可能出现的
        # status列表中, 则认为代理无效, 切换代理
        if response.status != 200:
            logger.info("response status not in spider.website_possible_httpstatus_list***********")
            new_request = request.copy()
            new_request.dont_filter = True

            return new_request
        else:
            logger.info('success')

            return response
    def process_exception(self, request, exception, spider):
        """
        处理由于使用代理导致的连接异常
        """
        logger.debug("%s exception: %s" % (request.meta["proxy"], exception))
        if isinstance(exception, self.DONT_RETRY_ERRORS):
            new_request = request.copy()
            new_request.dont_filter = True
            return new_request


class ProxyFetch(threading.Thread):
    def __init__(self,proxies,url):
        super(ProxyFetch,self).__init__()
        self.proxies=proxies
        self.url=url

    def run(self):
        '''
        根据不同的url，调取不同的网站获取方法，并将结果添加到proxies集合中
        '''
        self.proxies.update(getattr(self,'fetch_proxies_from_'+self.url)())

    def fetch_proxies_from_xici(self):
        proxies=set()
        url='http://www.xicidaili.com/nn/'
        try:
            for i in range(1,2):
                soup=self.get_soup(url+str(i))
                trs=soup.find('table',id="ip_list").find_all('tr')
                for i, tr in enumerate(trs):
                    if 0 == i:
                        continue
                    tds = tr.find_all('td')
                    ip = tds[1].string
                    port = tds[2].string
                    http_tpye = tds[5].string
                    #将端口、ip等拼接成完整的ip地址（下同）
                    proxy = ''.join([http_tpye, '://', ip, ':', port])
                    proxies.add(proxy)

        except Exception as e:
            logger.error('Failed to fetch_proxy_from_xici. Exception[%s]', e)

        return proxies

    def fetch_proxies_from_89ip(self):
        proxies = set()
        url = 'http://www.89ip.cn/tiqv.php?tqsl=20'
        try:
            soup_str = str(self.get_soup(url))
            ips = soup_str.split('<br/>')
            for ip in ips:
                pattern = re.compile(r'\b(?:25[0-5]\.|2[0-4]\d\.|[01]?\d\d?\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b:\d+')
                if len(ip) > 0:
                    proxy = 'http://' + pattern.findall(ip)[0]
                    proxies.add(proxy)

        except:
            pass

        return proxies

    def fetch_proxies_from_httpdaili(self):
        proxies = set()
        url = 'http://www.httpdaili.com/mfdl/'
        try:
            soup = self.get_soup(url)
            table = soup.find("div", attrs={"kb-item-wrap11"}).table
            trs = table.find_all("tr")
            for i in range(1, len(trs)):
                try:
                    tds = trs[i].find_all("td")
                    ip = tds[0].text
                    port = tds[1].text
                    type = tds[2].text
                    if type == u"匿名":
                        proxy = ''.join(['http://', ip, ':', port])
                        proxies.add(proxy)

                except:
                    pass
        except Exception as e:
            logger.error('Failed to fetch_proxy_from_httpdaili. Exception[%s]', e)

        return proxies
    def get_soup(self,url):
        user_agent = 'User-Agent,Mozilla/5.0'
        headers = {'user-agent': user_agent}
        try:
            r = requests.get(url, headers=headers,timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding
        except Exception as e:
            return 'error:', e

        soup = BeautifulSoup(r.text,'html.parser',from_encoding='utf-8')
        return soup

