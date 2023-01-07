from queue import Queue
from threading import Thread

import requests
from requests import Response

import config

from bgstally.constants import RequestMethod
from bgstally.debug import Debug

TIMEOUT_S = 10


class BGSTallyRequest:
    """
    Encapsulates a request that can be queued and processed in a thread
    """
    def __init__(self, endpoint:str, method:RequestMethod, callback:callable|None, headers:dict, stream:bool, payload:dict|None, data:dict|None):
        # The endpoint to call
        self.endpoint:str = endpoint
        # The type of request
        self.method:RequestMethod = method
        # A callback function to call when the response is received
        self.callback:callable|None = callback
        # Request headers
        self.headers:dict = headers
        # For requests with large content, True to stream in chunks
        self.stream:bool = stream
        # For requests that send data, a Dict containing the payload
        self.payload:dict|None = payload
        # Any additional data required to be passed to the callback function when the response is received
        self.data:dict|None = data


class RequestManager:
    """
    Handles the queuing and processing of requests
    """
    def __init__(self, bgstally):
        self.bgstally = bgstally

        self.request_queue:Queue = Queue()

        self.request_thread: Thread = Thread(target=self._worker, name="BGSTally Request worker")
        self.request_thread.daemon = True
        self.request_thread.start()


    def queue_request(self, endpoint:str, method:RequestMethod, callback:callable|None = None, headers:dict = {}, stream:bool = False, payload:dict|None = None, data:dict|None = None):
        """
        Add a request to the queue
        """
        headers:dict = {'User-Agent': f"{self.bgstally.plugin_name}/{self.bgstally.version}"} | headers

        self.request_queue.put(BGSTallyRequest(endpoint, method, callback, headers, stream, payload, data))


    def _worker(self) -> None:
        """
        Handle request thread work
        """
        Debug.logger.debug("Starting Request Worker...")

        while True:
            # Fetch from the queue. Blocks indefinitely until an item is available.
            request:BGSTallyRequest = self.request_queue.get()

            if not isinstance(request, BGSTallyRequest):
                Debug.logger.error(f"Queued request was not an instance of BGSTallyRequest")
                continue

            Debug.logger.info(f"Processing request {request.endpoint}")

            response:Response = None
            try:
                match request.method:
                    case RequestMethod.GET: response = requests.get(request.endpoint, headers=request.headers, stream=request.stream, timeout=TIMEOUT_S)
                    case RequestMethod.POST: response = requests.post(request.endpoint, headers=request.headers, stream=request.stream, json=request.payload, timeout=TIMEOUT_S)
                    case RequestMethod.PUT: response = requests.put(request.endpoint, headers=request.headers, stream=request.stream, json=request.payload, timeout=TIMEOUT_S)
                    case RequestMethod.DELETE: response = requests.delete(request.endpoint, headers=request.headers, stream=request.stream, timeout=TIMEOUT_S)
                    case RequestMethod.HEAD: response = requests.head(request.endpoint, headers=request.headers, stream=request.stream, timeout=TIMEOUT_S)
                    case RequestMethod.OPTIONS: response = requests.options(request.endpoint, headers=request.headers, stream=request.stream, timeout=TIMEOUT_S)
                    case _:
                        Debug.logger.warning(f"Invalid request method {request.type}")
                        if request.callback: request.callback(False, response, request)
                        continue

                response.raise_for_status()

            except requests.exceptions.RequestException as e:
                Debug.logger.warning(f"Unable to complete request {request.endpoint}", exc_info=e)
                if request.callback: request.callback(False, response, request)

            else:
                # Success
                Debug.logger.info(f"Request success {request.endpoint}")
                if request.callback: request.callback(True, response, request)
