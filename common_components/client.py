import json
import time
import os
from datetime import datetime as dt
from multiprocessing import JoinableQueue as Queue
from threading import Thread
import websockets
from bitfinex_connector.bitfinex_orderbook import BitfinexOrderBook
from gdax_connector.gdax_orderbook import GdaxOrderBook


class Client(Thread):

    def __init__(self, ccy, exchange):
        super(Client, self).__init__()
        self.sym = ccy
        self.exchange = exchange
        self.ws = None
        self.retry_counter = 0
        self.max_retries = 30
        self.last_subscribe_time = None
        self.queue = Queue(maxsize=1000)

        if self.exchange == 'gdax':
            self.request = json.dumps(dict(type='subscribe', product_ids=[self.sym], channels=['full']))
            self.request_unsubscribe = json.dumps(dict(type='unsubscribe', product_ids=[self.sym], channels=['full']))
            self.book = GdaxOrderBook(self.sym)
            self.trades_request = None
            self.ws_endpoint = 'wss://ws-feed.gdax.com'

        elif self.exchange == 'bitfinex':
            self.request = json.dumps({
                "event": "subscribe",
                "channel": "book",
                "prec": "R0",
                "freq": "F0",
                "symbol": self.sym,
                "len": "100"
            })
            self.request_unsubscribe = None
            self.trades_request = json.dumps({
                "event": "subscribe",
                "channel": "trades",
                "symbol": self.sym
            })
            self.book = BitfinexOrderBook(self.sym)
            self.ws_endpoint = 'wss://api.bitfinex.com/ws/2'
        # print('Client __init__ - Process ID: %s | Thread: %s' % (str(os.getpid()), self.name))

    async def unsubscribe(self):
        if self.exchange == 'gdax':
            await self.ws.send(self.request_unsubscribe)
            output = json.loads(await self.ws.recv())
            print('gdax - Client: Unsubscribe successful %s' % output)
        elif self.exchange == 'bitfinex':
            for channel in self.book.channel_id:
                request_unsubscribe = {
                    "event": "unsubscribe",
                    "chanId": channel
                }
                print('Client: %s unsubscription request sent:\n%s\n' % (self.sym, request_unsubscribe))
                await self.ws.send(request_unsubscribe)
                output = json.loads(await self.ws.recv())
                print('bitfinex - Client: Unsubscribe successful %s' % output)

    async def subscribe(self):
        """
        Subscribe to full order book
        :return: void
        """
        try:
            self.ws = await websockets.connect(self.ws_endpoint)

            await self.ws.send(self.request)
            print('BOOK %s: %s subscription request sent.' % (self.exchange, self.sym))

            if self.exchange == 'bitfinex':
                await self.ws.send(self.trades_request)
                print('TRADES %s: %s subscription request sent.' % (self.exchange, self.sym))

            self.last_subscribe_time = dt.now()

            while True:
                self.queue.put(json.loads(await self.ws.recv()))
                # print(self.book)

        except websockets.ConnectionClosed as exception:
            print('%s: subscription exception %s' % (self.exchange, exception))
            self.retry_counter += 1
            elapsed = (dt.now() - self.last_subscribe_time).seconds

            if elapsed < 5:
                sleep_time = max(5 - elapsed, 1)
                time.sleep(sleep_time)
                print('%s - %s is sleeping %i seconds...' % (self.exchange, self.sym, sleep_time))

            if self.retry_counter < self.max_retries:
                print('%s: Retrying to connect... attempted #%i' % (self.exchange, self.retry_counter))
                await self.subscribe()  # recursion
            else:
                print('%s: %s Ran out of reconnection attempts. Have already tried %i times.'
                      % (self.exchange, self.sym, self.retry_counter))

    def render_book(self):
        return self.book.render_book()

    def run(self):
        """
        Handle incoming level 3 data on a separate process
        (or process, depending on implementation)
        :return:
        """
        pass

