# Sage Santomenna, 2023/2024
# Helper class to faciliate use of an asynchronous web request client

import asyncio
import logging
import sys, os
import configparser
from bs4 import BeautifulSoup
import time
import concurrent.futures 
import logging
import httpx

executor = concurrent.futures.ThreadPoolExecutor(max_workers=1) 

class AsyncHelper:
    """!
    A helper class to facilitate easier asynchronous requesting.
    """

    def __init__(self, followRedirects: bool, max_simultaneous_requests, time_between_batches, do_heavy_logging, timeout=120):
        self.timeout = timeout
        self.client = httpx.AsyncClient(follow_redirects=followRedirects, timeout=self.timeout)
        self.max_simultaneous_requests = max_simultaneous_requests
        self.time_between_batches = time_between_batches
        self.do_heavy_logging = do_heavy_logging
        # formatter = logging.Formatter("%(asctime)s %(levelname)-5s | %(message)s", "%m/%d/%Y %H:%M:%S")
        # fileHandler = logging.FileHandler('async_utils.log')
        # fileHandler.setFormatter(formatter)
        # logger = logging.getLogger()
        # logger.addHandler(fileHandler)
        # logger.setLevel(logging.DEBUG if self.do_heavy_logging else logging.INFO)
        # self.logger = logger
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG if self.do_heavy_logging else logging.INFO)
        if not self.do_heavy_logging:
            httpx_logger = logging.getLogger("httpx")
            httpx_logger.setLevel(logging.WARNING)
            httpcore_logger = logging.getLogger("httpcore")
            httpcore_logger.setLevel(logging.WARNING)
        self.logger = logger

    def __del__(self):
        # Close connection when this object is destroyed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.client.aclose())
            else:
                loop.run_until_complete(self.client.aclose())
        except Exception:
            pass

    async def log(self, msg, info):
        try: 
           msg = msg + " | " + str(info)
        except:
           pass
        self.logger.info(msg)

    async def multiGet(self, URLlist, designations=None, soup=False, postContent=None, max_simultaneous_requests=None, time_between_batches=None):
        """!
        Asynchronously make multiple url requests. Optionally, turn the result into soup with beautifulSoup. Requires internet connection
        @param URLlist: A list of URLs to query
        @param designations: An optional list of designations to be paired with request results in the return dictionary. If none, urls will be used as designations
        @param soup: bool. If true, soup result before returning
        @param postContent: list. if not None, will post postContent instead of using get
        @param max_simultaneous_requests: int. The maximum number of simultaneous requests to make. If falsey, will make all requests at once
        @param time_between_batches: float. The time to wait between batches of requests, in seconds
        @return: dictionary of {desig/url: completed request} or {desig/url:html soup retrieved}
        """
        max_simultaneous_requests = max_simultaneous_requests or self.max_simultaneous_requests
        time_between_batches = time_between_batches or self.time_between_batches
        if designations is not None and len(designations) != len(URLlist):
            raise ValueError("asyncMultiRequest: provided designation length does not match url list length")
        if postContent is not None and len(postContent) != len(URLlist):
            raise ValueError("asyncMultiRequest: provided postContent length does not match url list length")

        if designations is None:
            designations = URLlist
        if postContent is None:
            postContent = [None] * len(URLlist)
        tasks = []
        result = []
        if not max_simultaneous_requests or len(URLlist) <= max_simultaneous_requests:
            for i, url in enumerate(URLlist):
                tasks.append(
                    asyncio.create_task(self.makeRequest(designations[i], url, soup=soup, postContent=postContent[i])))
            result = await asyncio.gather(*tasks)
        else:
            max_simultaneous_requests = min(max_simultaneous_requests, len(URLlist))
            self.logger.info(f"Making {len(URLlist)} requests in groups of {max_simultaneous_requests}")
            i = 0
            # limit the number of max simultaneous requests for rate limiting reasons
            while (i+1)*max_simultaneous_requests < len(URLlist):
                self.logger.info(f"Querying from {i*max_simultaneous_requests} to {(i+1)*max_simultaneous_requests}")
                tasks = []
                for j in range(i*max_simultaneous_requests,(i+1)*max_simultaneous_requests):
                    tasks.append(
                        asyncio.create_task(self.makeRequest(designations[j], URLlist[j], soup=soup, postContent=postContent[j])))
                i += 1
                r = await asyncio.gather(*tasks)
                # self.logger.info("r in multiGet:"+ str(r))
                result.extend(r)
                # self.logger.info(result)
                time.sleep(time_between_batches)
            # TODO: MAKE SURE the i vs i+1 is correct here
            if i * max_simultaneous_requests < len(URLlist)-1:
                self.logger.info(f"Querying from {i*max_simultaneous_requests} to {len(URLlist)}")
                tasks = []
                for j in range(i*max_simultaneous_requests, len(URLlist)):
                    tasks.append(
                        asyncio.create_task(self.makeRequest(designations[j], URLlist[j], soup=soup, postContent=postContent[j])))
                r = await asyncio.gather(*tasks, return_exceptions=True)
                # self.logger.info("r in multiGet: "+ str(r))
                result.extend(r)

        # gather tuples returned into dictionary, return
        # self.logger.info("final result from multiGet: "+str(result))
        returner = dict()
        for desig, item in result:
            returner.setdefault(desig, []).append(item)
        return returner

    async def post_with_redirect(self, url, **kwargs):
        response = await self.client.post(url, follow_redirects=False, **kwargs)
        if response.status_code == 302:
            redirect_url = response.headers["Location"]
            response = await self.client.post(redirect_url, **kwargs)
        return response

    async def makeRequest(self, desig, url, soup=False, postContent=None):
        """!
        Asynchronously GET or POST to the indicated URL. Optionally, turn the result into soup with beautifulSoup. Calling this in a for loop probably won't work like you want it to, use multiGet for concurrent requests
        @param desig: An identifying designation for the html retrieved
        @param url: The URL to query
        @param soup: bool. If true, soup result before returning
        @param postContent: list. if not none, will POST postContent instead of using get
        @return: A tuple, (desig, completedRequest) or (desig,soup(completedRequest))
        """
        # if HEAVY_LOGGING is true, log an absurd amount of detail about the web requests: 
        extensions = {"trace": self.log} if self.do_heavy_logging else {}
        
        try:
            try:
                if postContent is not None:
                    offsetReq = await self.post_with_redirect(url, data=postContent, extensions=extensions)
                    # offsetReq = await self.client.post(url, data=postContent, extensions=extensions)
                else:
                    offsetReq = await self.client.get(url, extensions=extensions)
            except RuntimeError:
                self.client = httpx.AsyncClient(follow_redirects=True, timeout=self.timeout) # make new client
                if postContent is not None:
                    offsetReq = await self.post_with_redirect(url, data=postContent, extensions=extensions)
                else:
                    offsetReq = await self.client.get(url, extensions=extensions)
        except (httpx.TimeoutException, httpx.ReadTimeout):
            self.logger.error(f"Async request timed out. Timeout is set to {str(self.timeout)} seconds.")
            return desig, None
        except (httpx.ConnectError, httpx.HTTPError) as e:
            self.logger.error(f"HTTP error. Unable to make async request to {url}: {e}")
            self.logger.error(f"{e.__dict__}")
            # raise e
            return desig, None

        # self.logger.info("offsetReq: "+ str(offsetReq.__dict__))
        if offsetReq.status_code != 200:
            self.logger.error(f"Error: HTTP status code {str(offsetReq.status_code)} . Unable to make async request to {url}. Reason given: {offsetReq.reason_phrase}")
            return desig, None
        if soup:
            offsetReq = BeautifulSoup(offsetReq.content, 'html.parser')
        return tuple([desig, offsetReq])
