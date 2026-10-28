"""HTTP 公共参数：代理、SSL、超时。"""

import urllib3

from config import SSL_VERIFY, HTTP_PROXY, HTTPS_PROXY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def request_kwargs():
    kwargs = {"verify": SSL_VERIFY, "timeout": 30}
    proxies = {}
    if HTTP_PROXY:
        proxies["http"] = HTTP_PROXY
    if HTTPS_PROXY:
        proxies["https"] = HTTPS_PROXY
    if proxies:
        kwargs["proxies"] = proxies
    return kwargs
