# coding=utf-8
#
import time
import copy
import pytest
import logging
import unittest
import threading
import concurrent.futures

from multiprocessing import Manager
from soocii_pubsub_lib import pubsub_client, sub_service

# ========== Initial Logger ==========
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)-15s][%(thread)d][%(levelname)-5s][%(filename)s][%(funcName)s#%(lineno)d] %(message)s')
logger = logging.getLogger(__name__)
# ====================================


# normal subscribe
@pytest.mark.usefixtures("start_emulator")
class NormalSubscribeTests(unittest.TestCase):
    def setUp(self):
        self.project = 'fake-project'
        self.cred = None
        self.topic = 'fake-topic'
        self.published_message_id = None
        # self.received_message = None
        # self.received_message_counts = 0
        self.service = None

        # shared variables due to multi-threading
        manager = Manager()
        self.lock = threading.Lock()
        self.received_message = manager.dict()
        self.received_message_counts = manager.Value('i', 0)

    def tearDown(self):
        pass

    def __on_published(self, message_id):
        logger.info('message is published with message id: {}'.format(message_id))
        self.published_message_id = message_id

    def __on_received(self, message):
        try:
            with self.lock:
                logger.info('message is received with payload: {}'.format(message))
                self.received_message = copy.deepcopy(message)
                self.received_message_counts.value = self.received_message_counts.value + 1
                logger.info('received_message: {}, received_message_counts: {}'.format(self.received_message, self.received_message_counts.value))
        except Exception as e:
            logger.exception('unexpected exception was caughted: {}'.format(e))
        # ack message
        logger.info('ack message')
        return True

    def __publisher(self):
        # prepare publisher
        publisher = pubsub_client.PublisherClient(self.project, self.cred)
        # get configuration of the topic before sending request
        exception_caughted = False
        try:
            publisher.get_topic(self.topic)
        except Exception as e:
            exception_caughted = True
            logger.exception('unexpected exception was caughted: {}'.format(e))
        self.assertFalse(exception_caughted)
        # publish bytes
        logger.info('start publishing message')
        for _ in range(5):
            publisher.publish(self.topic, b'bytes data', callback=lambda message_id: self.__on_published(message_id))
            time.sleep(0.5)

    def __subscriber(self):
        # prepare subscriber
        self.subscription = pubsub_client.SubscribeClient(self.project, self.cred)
        self.subscription.create_subscription(self.topic, 'fake-subscription')
        self.service = sub_service.SubscriptionService(self.subscription)
        logger.info('start subscribing message')
        self.service.run(callback=lambda message: self.__on_received(message))

    def __waitter(self):
        # wait for callback
        time.sleep(10)
        self.service.shutdown()

    # @pytest.mark.skip(reason="not reliable in travis CI")
    def test_subscribe_message(self):
        # prepare publisher
        publisher = pubsub_client.PublisherClient(self.project, self.cred)
        publisher.create_topic(self.topic)
        # prepare subscriber
        self.subscription = pubsub_client.SubscribeClient(self.project, self.cred)
        self.subscription.create_subscription(self.topic, 'fake-subscription')

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(lambda: self.__waitter())
            self.__publisher()
            # subscriber service MUST run in main thread
            self.__subscriber()

        # verify if message has been received
        assert self.received_message is not None
        assert self.received_message['data'] == b'bytes data'
        assert self.received_message['attributes'] == {}
        assert self.received_message_counts.value == 5
