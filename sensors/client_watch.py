import json
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import time

from st2reactor.sensor.base import PollingSensor

TRIGGER_CLIENT_CHANGE = 'unifi.ClientChange'


class ClientWatchSensor(PollingSensor):

    def setup(self):
        self._logger = self._sensor_service.get_logger(__name__)

        # Need to be CAREFUL with interval. Uptime for clients on the back-end
        # seems to be updated at its own intervals, so consecutive API calls
        # may show exactly the same uptime even if client is still online.
        #
        # 30 seconds seems to be a good interval to use for this sensor
        # to avoid this problem
        self._poll_interval = 30

        try:
            self.username = self._config['username']
            self.password = self._config['password']
            self.hostname = self._config['hostname']
            self.port = str(self._config['port'])
        except KeyError:
            self._logger.error("Pack not configured properly.")
            raise

        self.clients_to_watch = self._config['clients_to_watch']

        self.last_client_storage = {}

        self.first_pass_flag = {'value': True}

        # Retrieve an initial list of clients, so polling can start with
        # a copy to compare with
        for client in self._get_clients():

            # Store initial record (without 'online' key)
            self.last_client_storage[client['mac']] = {
                "uptime": client.get('uptime')
            }

        # Want to do a poll interval sleep here so we don't get
        # any strange behavior from polling twice in rapid succession
        time.sleep(self._poll_interval)

    def poll(self):
        clients = self._get_clients()

        # TODO(mierdin) Need to do some testing using some clients that
        # both are and aren't being watched, that came online AFTER
        # this sensor was started
        for client in clients:

            this_mac = client.get('mac')
            alias = self._get_alias(this_mac)

            if this_mac in [wc.get('mac') for wc in self.clients_to_watch]:

                # TODO (mierdin): Get alias out of list and augment below logging
                # OR just scrap the whole idea, I mean we DO have hostname (though
                # not always reliable)

                if this_mac not in self.last_client_storage:

                    # Store initial record (without 'online' key)
                    self.last_client_storage[client['mac']] = {
                        "uptime": client.get('uptime')
                    }
                    continue

                # Determine if client is CURRENTLY online or offline
                if client.get('uptime') != self.last_client_storage[this_mac]['uptime']:
                    self._logger.debug(
                        "Client %s (%s) updated uptime from %s to %s - ONLINE" % (
                            this_mac,
                            alias,
                            self.last_client_storage[this_mac]['uptime'],
                            client.get('uptime')
                        )
                    )
                    online = True
                else:
                    self._logger.debug(
                        "Client %s (%s) uptime remained the same: %s to %s - OFFLINE" % (
                            this_mac,
                            alias,
                            self.last_client_storage[this_mac]['uptime'],
                            client.get('uptime')
                        )
                    )
                    online = False

                # If the 'online' key is not defined in this dict, it means we only have an initial
                # record for this client, so we don't have enough info to make a comparison yet.
                if 'online' in self.last_client_storage[this_mac]:

                    # Based on current and last status, determine if client is
                    # undergoing a transition
                    last_online_status = self.last_client_storage[this_mac]['online']
                    if last_online_status != online:
                        self._logger.info("New client %s online status: %s" % (this_mac, online))
                        payload = {
                            "alias": alias,
                            "online": online,
                            "client_info": client
                        }
                        self._sensor_service.dispatch(
                            trigger=TRIGGER_CLIENT_CHANGE,
                            payload=payload
                        )

                self.last_client_storage[this_mac] = {
                    "uptime": client.get('uptime'),
                    "online": online
                }

    def _get_clients(self):
        """Function for retrieving a list of clients

        No stable, actively maintained library currently exists for
        working with the Unifi API, likely a byproduct of the fact that
        this API is not officially supported by them.

        While evaluating whether or not this is something I want to take on
        myself, I just through together a quick solution with "requests".
        It works, but this should definitely get moved into it's own library
        in the near future.
        """

        session = requests.Session()

        params = {'username': self.username, 'password': self.password}
        session.post("https://%s:%s/api/login" % (
            self.hostname,
            self.port
        ), json.dumps(params), verify=False)

        clients_resp = session.get("https://%s:%s/api/s/default/stat/sta" % (
            self.hostname,
            self.port
        ), verify=False)
        clients = clients_resp.json()['data']

        return clients

    def _get_alias(self, mac):
        for watched_client in self.clients_to_watch:
            if watched_client.get('mac') == mac:
                return watched_client.get('alias')

    def cleanup(self):
        # This is called when the st2 system goes down. You can perform cleanup operations like
        # closing the connections to external system here.
        pass

    def add_trigger(self, trigger):
        # This method is called when trigger is created
        pass

    def update_trigger(self, trigger):
        # This method is called when trigger is updated
        pass

    def remove_trigger(self, trigger):
        # This method is called when trigger is deleted
        pass
