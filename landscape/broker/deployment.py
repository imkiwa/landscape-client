"""Deployment code for the broker."""

import os

from landscape.deployment import LandscapeService, run_landscape_service
from landscape.broker.store import get_default_message_store
from landscape.broker.transport import HTTPTransport
from landscape.broker.exchange import MessageExchange
from landscape.broker.registration import RegistrationHandler, Identity
from landscape.broker.broker import BrokerDBusObject
from landscape.lib.fetch import fetch_async
from landscape.broker.ping import Pinger


class BrokerService(LandscapeService):
    """The core C{Service} of the Landscape Broker C{Application}.

    The Landscape broker service handles all the communication between the
    client and server. When started it creates and runs all necessary components
    to exchange messages with the Landscape server.

    @ivar persist_filename: Path to broker-specific persisted data.
    @ivar persist: A L{Persist} object saving and loading from
        C{self.persist_filename}.
    @ivar message_store: A L{MessageStore} used by the C{exchanger} to
        queue outgoing messages.
    @ivar transport: A L{HTTPTransport} used by the C{exchanger} to deliver messages.
    @ivar identity: The L{Identity} of the Landscape client the broker runs on.
    @ivar exchanger: The L{MessageExchange} exchanges messages with the server.
    @ivar pinger: The L{Pinger} checks if the server has new messages for us.
    @ivar registration: The L{RegistrationHandler} performs the initial
        registration.

    @cvar service_name: C{"broker"}
    """

    transport_factory = HTTPTransport
    service_name = "broker"

    def __init__(self, config):
        """
        @param config: a L{BrokerConfiguration}.
        """
        self.persist_filename = os.path.join(
            config.data_path, "%s.bpickle" % (self.service_name,))
        super(BrokerService, self).__init__(config)
        self.transport = self.transport_factory(config.url,
                                                config.ssl_public_key)

        self.message_store = get_default_message_store(
            self.persist, config.message_store_path)
        self.identity = Identity(self.config, self.persist)
        self.exchanger = MessageExchange(self.reactor, self.message_store,
                                         self.transport, self.identity,
                                         config.exchange_interval,
                                         config.urgent_exchange_interval)

        self.pinger = Pinger(self.reactor, config.ping_url, self.identity,
                             self.exchanger)
        self.registration = RegistrationHandler(config,
                                                self.identity, self.reactor,
                                                self.exchanger,
                                                self.pinger,
                                                self.message_store,
                                                fetch_async)

        self.reactor.call_on("post-exit", self._exit)

    def _exit(self):
        # Our reactor calls the Twisted reactor's crash() method rather
        # than the real stop.  As a consequence, if we use it here, normal
        # termination doesn't happen, and stopService() would never get
        # called.
        from twisted.internet import reactor
        reactor.stop()

    def startService(self):
        """Start the broker.

        Create the DBus-published L{BrokerDBusObject}, and start
        the L{MessageExchange} and L{Pinger} services.

        If the configuration specifies the bus as 'session', the DBUS
        message exchange service will use the DBUS Session Bus.
        """
        super(BrokerService, self).startService()
        self.dbus_object = BrokerDBusObject(self.config, self.reactor,
                                            self.exchanger, self.registration,
                                            self.message_store, self.bus)

        self.exchanger.start()
        self.pinger.start()

    def stopService(self):
        """Stop the broker."""
        self.exchanger.stop()
        super(BrokerService, self).stopService()


def run(args):
    """Run the application, given some command line arguments."""
    run_landscape_service(BrokerConfiguration, BrokerService, args,
                          BrokerDBusObject.bus_name)
