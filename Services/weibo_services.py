# -*- coding:utf-8 -*-
import requests
import json
import time
from BasicAPI.weibo_op import WeiboOp
import random
from BasicAPI.weibo_login_simulation import WeiboLoginSimulation
import logging
from lxml import html
import threading
from log import Logger
import settings
import traceback

class WeiboServices:

    def __init__(self):
        self.log = Logger('../Sources/logs/wbservices.log', logging.DEBUG, logging.DEBUG)

    def ask_tuling(self, info, uid):
        url = "http://www.tuling123.com/openapi/api"
        payload = {
            "key": "ecc197ec863843be981fed5eb4283adf",
            "info": info,
            "userid": uid,
        }

        res = requests.post(url, data=payload)
        reply = json.loads(res.text)# 图灵回复的json

        reply_content = {"text": None, "icon": None}

        if reply["code"] == 100000:
            reply_content["text"] = reply["text"]

        elif reply["code"] == 200000:
            reply_content["text"] = "%s \n%s" % (reply["text"], reply["url"])

        elif reply["code"] == 308000:
            detail = ""
            for ob in reply["list"]:
                detail += "%s: %s; \n" % (ob["name"], ob["detailurl"])

            reply_content["text"] = "%s \n%s" % (reply["text"], detail)

            if "icon" in reply["list"][0] and reply["list"][0]["icon"].strip() != "":
                reply_content["icon"] = reply["list"][0]["icon"]

        elif reply["code"] == 302000:
            detail = ""
            for ob in reply["list"]:
                detail += "%s: %s; \n" % (ob["article"], ob["detailurl"])

            reply_content["text"] = "%s \n%s" % (reply["text"], detail)

            if "icon" in reply["list"][0] and reply["list"][0]["icon"].strip() != "":
                reply_content["icon"] = reply["list"][0]["icon"]

        return reply_content

    def listen_all_friends(self, mid_last, listener, sofa=True):
        url = "https://m.weibo.cn/feed/friends?version=v4"
        wbop = WeiboOp(listener["session"])
        # headers = wbop.get_headers_mobile(listener[1].cookies.items())

        while True:
            try:
                res = listener["session"].get(url)
            except Exception as e:
                print(e)
                time.sleep(10)
                continue

            res.encoding = "gb2312"
            print(res.text)
            res_json = res.json()
            cards = res_json[0]["card_group"]
            card_last = None
            for c in cards:
                if "card_type" in c and c["card_type"] == 9:
                    card_last = c

            blog = card_last["mblog"]
            print("监听 %s" % blog["user"]["screen_name"])

            if int(blog["mid"]) > int(mid_last):
                reply_text = u"沙发!为了橘子树！"

                if not sofa:
                    # 过滤html标签
                    t = html.fromstring(blog["text"])
                    blog_text = t.xpath('string(.)')

                    reply_text = self.ask_tuling(blog_text, blog["user"]["id"])

                print("%s 更新了: %s" % (blog["user"]["screen_name"], blog["text"]))
                if wbop.comment_forward(blog["mid"], listener["uid"], reply_text, "0"):
                    mid_last = blog["mid"]

            random.seed(time.time())

            sleep_time = 1 + random.random() * 5
            time.sleep(sleep_time)
            print("间隔 %d" % sleep_time)

    def listen_user(self, listener, uid_listened, reply_text=None, reply_icon=None, mid_last=None):
        '''
        # 监听单个用户，抢沙发
        :param listener: 一个dict {"uid": ,"session": , }
        :param uid_listened: 监听的用户id
        :param sofa:
        :param mid_last:
        :return:
        '''
        url = "https://m.weibo.cn/api/container/getIndex?type=uid&value=%s&containerid=107603%s&page=1" % (uid_listened, uid_listened)
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip,deflate,br",
            "Accept-Language": "zh-CN,zh;q=0.8",
            "Connection": "keep-alive",
            "Host": "weibo.com",
            "Upgrade-Insecure - Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.86 Safari/537.36",
        }
        while True:
            try:
                res = requests.get(url, headers)
                cards = json.loads(res.text)["data"]["cards"]

                card_last = cards[0]
                blog = card_last["mblog"]
                print("持续监听 %s" % blog["user"]["screen_name"])

                if mid_last is None: # 如果没有指定最新的微博，则把当前收到的最新微博作为标准进行监听
                    mid_last = blog["mid"]

                if int(blog["mid"]) > int(mid_last):
                    if reply_text is None:# 不是抢沙发，就用机器人智能回复
                        # 过滤html标签
                        t = html.fromstring(blog["text"])
                        blog_text = t.xpath('string(.)')

                        reply_content = self.ask_tuling(blog_text, blog["user"]["id"])
                        reply_text = reply_content["text"]
                        reply_icon = reply_content["icon"]

                    print("%s 更新了: %s" % (blog["user"]["screen_name"], blog["text"]))

                    wbop = WeiboOp(listener["uid"], session=listener["session"])
                    comment_res = wbop.comment_forward(blog["mid"], reply_text, False, reply_icon)

                    if comment_res["code"] == "100000":
                        mid_last = blog["mid"]
                        # 成功评论，记录到日志
                        self.log.debug(u'评论了 %s 的微博 "%s" : %s' %(blog["user"]["screen_name"], blog["text"], reply_text))
                    elif comment_res["code"] == "100001" and u"隔十分钟" in comment_res["msg"]:
                        sleep_time = 10 * 60
                        print("睡眠间隔 %d" % sleep_time)
                        time.sleep(sleep_time)

                random.seed(time.time())
                sleep_time = 1 + random.random() * 5
                # print("睡眠间隔 %d" % sleep_time)

                time.sleep(sleep_time)
            except Exception as e:
                traceback.print_exc()
                self.log.error(str(e))
                time.sleep(10)
                continue

    # 监听多个微博用户，抢沙发
    def listen_users(self, listener, uid_2_reply_text, uid_2_reply_icon):
        '''
        :param listener: 登录的user对象
        :param uid_2_reply_text: {uid: reply_text}
        :return:
        '''
        t_map = {}
        for uid, reply_text in uid_2_reply_text.items():
            t = threading.Thread(target=self.listen_user, args=(listener, uid, reply_text, uid_2_reply_icon[uid]), name=uid)
            t.start()
            t_map[uid] = t

        while True: # 主线程死循环阻塞，负责监控其他线程
            print("当前活跃线程数目： %d" % threading.active_count())
            if threading.active_count() - 1 < len(uid_2_reply_text.items()): # 发现某个线程被杀死了，进行检查并再次实例化对应uid的线程，-1是减掉主线程
                for uid, thread in t_map.items():
                    if thread is None:
                        t = threading.Thread(target=self.listen_user, args=(listener, uid, uid_2_reply_text[uid], uid_2_reply_icon[uid]), name=uid)
                        t.start()
                        t_map[uid] = t
            time.sleep(3)

    # 从热门里爬出用户uid
    def get_uid_list_hot(self, pg_end = 3000):
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip,deflate,br",
            "Accept-Language": "zh-CN,zh;q=0.8",
            "Connection": "keep-alive",
            "Host": "m.weibo.cn",
            "Cookie": "_T_WM=7329ff8d0f86ecba0746c214881dc834; WEIBOCN_FROM=1110006030; M_WEIBOCN_PARAMS=luicode%3D10000011%26lfid%3D102803%26fid%3D102803%26uicode%3D10000011",
            "Referer": "https://m.weibo.cn/p/index?containerid=102803",
            "Upgrade-Insecure - Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.86 Safari/537.36",
        }

        uid_list = []

        for p in range(pg_end):
            cards = None
            try:
                url = "https://m.weibo.cn/api/container/getIndex?containerid=102803&since_id=%d" % (p+1)
                print(url)
                res = requests.get(url, headers)
                cards = json.loads(res.text)["data"]["cards"]
            except Exception as e:
                print(e)
                continue

            if cards is not None:
                for c in cards:
                    if "card_type" in c and c["card_type"] == 9:
                        uid_list.append({"uid": str(c["mblog"]["user"]["id"]), "name": c["mblog"]["user"]["screen_name"]})

            print("爬完第%d页" % p)
        return uid_list

    def random_wait(self, base=settings.DELAY):
        random.seed(time.time())
        sleeptime = base + 30 * random.random()
        print("sleep %ds" % sleeptime)
        time.sleep(sleeptime)

    # 给微博刷赞
    def batch_like_blog(self, level, num, mid, interval=settings.DELAY):
        accounts = self.db.get_accounts(level)

        random.shuffle(accounts)

        ind = 0
        num_accounts = len(accounts)

        while True:
            if ind >= num_accounts or num == 0: break

            account = accounts[ind]
            ind += 1

            cookies_dict = json.loads(account[0])
            uid = account[1]
            wbop = WeiboOp(uid, cookies=cookies_dict)
            if wbop.like_blog(mid):
                num -= 1

            self.random_wait(interval)

    def batch_comment_blog(self, level, mid, interval, comments):
        accounts = self.db.get_accounts(level)
        c_nums = len(comments)
        if c_nums > len(accounts):
            logging.warning("excessive nums of comments")
            return False

        accounts_sample = random.sample(accounts, c_nums)
        for ind, account in enumerate(accounts_sample):
            cookies_dict = json.loads(account[0])
            uid = account[1]
            wbop = WeiboOp(uid, cookies=cookies_dict)

            wbop.comment_forward(mid, comments[ind], "0")
            self.random_wait(interval)

    # 批量删除mid_end之前的微博
    def batch_delete(self, user, mid_end):
        url = "https://m.weibo.cn/api/container/getIndex?type=uid&value=%s&containerid=107603%s&page=1" % (user["uid"], user["uid"])
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip,deflate,br",
            "Accept-Language": "zh-CN,zh;q=0.8",
            "Connection": "keep-alive",
            "Host": "weibo.com",
            "Upgrade-Insecure - Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.86 Safari/537.36",
        }

        res = requests.get(url, headers)
        jsob = None

        try:
            jsob = json.loads(res.text)
        except:
            logging.warning("返回结果不是json 格式")
            return

        num = jsob["data"]["cardlistInfo"]["total"]
        pages = num // 10 + 1

        mids_wf_del = []

        for p in range(pages):
            url = "https://m.weibo.cn/api/container/getIndex?type=uid&value=%s&containerid=107603%s&page=%d" % (
            user["uid"], user["uid"], p + 1)

            res = requests.get(url, headers)
            jsob = None

            try:
                jsob = json.loads(res.text)
            except:
                logging.warning("返回结果不是json 格式")
                logging.info("%s " % res.text)
                return

            cards = jsob["data"]["cards"]

            for card in cards:
                if card["card_type"] == 9 and card["mblog"]["id"] <= mid_end:
                    mids_wf_del.append(card["mblog"]["id"])


        wbop = WeiboOp(user["uid"], user["session"])
        for mid in mids_wf_del:
            wbop.del_blog(mid)

if __name__ == "__main__":
    ws = WeiboServices()

    wblg = WeiboLoginSimulation()
    user = wblg.login_simulate("15850782585", "Weibo6981228,,,") # 模拟登录
    # wbop = WeiboOp(user["uid"], user["session"])
    # wbop.comment_forward("4463822079498814", "自测发图hhhh", forward=False, img_url="../Sources/img/door.png")

    # 成果：1927305954
    # 犬来八荒: 7347878145
    # 自己：6219737121
    uid_2_reply_text = {
        "1927305954": "狗哥的沙发我承包了，弟弟们还有什么想说的？",
        "7347878145": "狗哥的沙发我承包了，弟弟们还有什么想说的？",
        "6219737121": "狗哥的沙发我承包了，弟弟们还有什么想说的？",
    }
    uid_2_reply_icon = {
        "1927305954": "../Sources/img/jiuzheyang.jpg",
        "7347878145": "../Sources/img/jiuzheyang.jpg",
        "6219737121": "../Sources/img/jiuzheyang.jpg",
    }
    # ws.listen_user(user, "6219737121", "沙发", "../Sources/img/jiuzheyang.jpg")
    ws.listen_users(user, uid_2_reply_text, uid_2_reply_icon)

    # wbop.reply_comment("4463794787037289", "4221453844425270", "...",)
    # ws.batch_delete(user, "4123769540944819")

    # comments = [
    #     u"颤抖吧朱军桥！！！",
    #     u"敌军还有10s到达战场...",
    #     u"即将对该微博发起分布式点赞",
    #     u"为军桥欧巴疯狂打call，此条5毛",
    #     u"今天尾号666的开始笑",
    #     u"我是pgone的小号，可以做你弟弟吗",
    #     u"演唱会vip黄牛票要伐？给你优惠噻",
    #     u"insta360倒闭了，无良老板携投资款带着小姨子跑路了",
    #     u"老子张伊扬！",
    #     u"滴，学生卡",
    # ]

    # ws.vast_comment_blog(3, "4204871458714716", 10, comments)
    # ws.batch_like_blog(3, 10, "4204871458714716")

    # wblgs = WeiboLoginSimulation()
    # user = wblgs.login_simulate("15850782585", "Weibo6981228.")
    # # user = wblgs.login_simulate("18244808530", "WWWEEE6981228.")
    # session = user["session"]
    # wbop = WeiboOp(user["uid"], cookies=session.cookies.get_dict())
    # ws.listen_users(user,
    #                 ["1677856077", "1669879400", "1537790411", "1712570933", "3228634923", "1784537661", "3856976436"])

    # pid = wbop.up_img("./cover.jpg")
    # pid = wbop.up_img("http://i4.xiachufang.com/image/280/cb1cb7c49ee011e38844b8ca3aeed2d7.jpg")
    # wbop.comment_forward("4196060278136857", "再测试一下", "0", pid)
    # ws.listen_user(user, "2764602935", sofa=False)


    # uid_list = ws.get_uid_list_hot(10)
    # print(len(uid_list))
    # for u in uid_list:
    #     print("%s %s" % (u["uid"], u["name"]))

    # ws.listen_user("1669879400", "4200018053211484", user, sofa=True)# 迪丽热巴

    # ws.listen_all_friends("4200247808521037", user, sofa=False)
