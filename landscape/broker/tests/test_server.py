from twisted.internet.defer import succeed, fail

from landscape.manager.manager import FAILED
from landscape.tests.helpers import LandscapeTest, DEFAULT_ACCEPTED_TYPES
from landscape.broker.tests.helpers import (
    BrokerServerHelper, RemoteClientHelper)


class FakeClient(object):
    pass


class FakeCreator(object):

    def __init__(self, reactor, config):
        pass

    def connect(self):
        return succeed(FakeClient())


class BrokerServerTest(LandscapeTest):

    helpers = [BrokerServerHelper]

    def test_ping(self):
        """
        The L{BrokerServer.ping} simply returns C{True}.
        """
        self.assertTrue(self.broker.ping())

    def test_send_message(self):
        """
        The L{BrokerServer.send_message} method forwards a message to the
        broker's exchanger.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        self.broker.send_message(message)
        self.assertMessages(self.mstore.get_pending_messages(), [message])
        self.assertFalse(self.exchanger.is_urgent())

    def test_send_message_with_urgent(self):
        """
        The L{BrokerServer.send_message} can optionally specify the urgency
        of the message.
        """
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        self.broker.send_message(message, True)
        self.assertMessages(self.mstore.get_pending_messages(), [message])
        self.assertTrue(self.exchanger.is_urgent())

    def test_is_pending(self):
        """
        The L{BrokerServer.is_pending} method indicates if a message with
        the given id is pending waiting for delivery in the message store.
        """
        self.assertFalse(self.broker.is_message_pending(123))
        message = {"type": "test"}
        self.mstore.set_accepted_types(["test"])
        message_id = self.broker.send_message(message)
        self.assertTrue(self.broker.is_message_pending(message_id))

    def test_register_client(self):
        """
        The L{BrokerServer.register_client} method can be used to register
        client components that need to communicate with the server. After
        the registration they can be fetched with L{BrokerServer.get_clients}.
        """
        self.assertEquals(self.broker.get_clients(), [])
        self.assertEquals(self.broker.get_client("test"), None)
        self.assertEquals(self.broker.get_connectors(), [])
        self.assertEquals(self.broker.get_connector("test"), None)

        def assert_registered(ignored):
            self.assertEquals(len(self.broker.get_clients()), 1)
            self.assertEquals(len(self.broker.get_connectors()), 1)
            self.assertTrue(
                isinstance(self.broker.get_client("test"), FakeClient))
            self.assertTrue(
                isinstance(self.broker.get_connector("test"), FakeCreator))

        self.broker.connectors_registry = {"test": FakeCreator}
        result = self.broker.register_client("test")
        return result.addCallback(assert_registered)

    def test_stop_clients(self):
        """
        The L{BrokerServer.stop_clients} method calls the C{exit} method
        of each registered client, and returns a deferred resulting in C{None}
        if all C{exit} calls were successful.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        for client in self.broker.get_clients():
            client.exit = self.mocker.mock()
            self.expect(client.exit()).result(succeed(None))
        self.mocker.replay()
        return self.assertSuccess(self.broker.stop_clients())

    def test_stop_clients_with_failure(self):
        """
        The L{BrokerServer.stop_clients} method calls the C{exit} method
        of each registered client, and returns a deferred resulting in C{None}
        if all C{exit} calls were successful.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        [client1, client2] = self.broker.get_clients()
        client1.exit = self.mocker.mock()
        client2.exit = self.mocker.mock()
        self.expect(client1.exit()).result(succeed(None))
        self.expect(client2.exit()).result(fail(Exception()))
        self.mocker.replay()
        return self.assertFailure(self.broker.stop_clients(), Exception)

    def test_reload_configuration(self):
        """
        The L{BrokerServer.reload_configuration} method forces the config
        file associated with the broker server to be reloaded.
        """
        open(self.config_filename, "a").write("computer_title = New Title")
        result = self.broker.reload_configuration()
        result.addCallback(lambda x: self.assertEquals(
            self.config.computer_title, "New Title"))
        return result

    def test_reload_configuration_stops_clients(self):
        """
        The L{BrokerServer.reload_configuration} method forces the config
        file associated with the broker server to be reloaded.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        for client in self.broker.get_clients():
            client.exit = self.mocker.mock()
            self.expect(client.exit()).result(succeed(None))
        self.mocker.replay()
        return self.assertSuccess(self.broker.reload_configuration())

    def test_register(self):
        """
        The L{BrokerServer.register} method attempts to register with the
        Landscape server and waits for a C{set-id} message from it.
        """
        registered = self.broker.register()
        # This should callback the deferred.
        self.exchanger.handle_message({"type": "set-id", "id": "abc",
                                       "insecure-id": "def"})
        return self.assertSuccess(registered)

    def test_get_accepted_types_empty(self):
        """
        The L{BrokerServer.get_accepted_message_types} returns an empty list
        if no message types are accepted by the Landscape server.
        """
        self.mstore.set_accepted_types([])
        self.assertEquals(self.broker.get_accepted_message_types(), [])

    def test_get_accepted_message_types(self):
        """
        The L{BrokerServer.get_accepted_message_types} returns the list of
        message types accepted by the Landscape server.
        """
        self.mstore.set_accepted_types(["foo", "bar"])
        self.assertEquals(sorted(self.broker.get_accepted_message_types()),
                          ["bar", "foo"])

    def test_get_server_uuid_with_unset_uuid(self):
        """
        The L{BrokerServer.get_server_uuid} method returns C{None} if the uuid
        of the Landscape server we're pointing at is unknown.
        """
        self.assertEquals(self.broker.get_server_uuid(), None)

    def test_get_server_uuid(self):
        """
        The L{BrokerServer.get_server_uuid} method returns the uuid of the
        Landscape server we're pointing at.
        """
        self.mstore.set_server_uuid("the-uuid")
        self.assertEquals(self.broker.get_server_uuid(), "the-uuid")

    def test_register_client_accepted_message_type(self):
        """
        The L{BrokerServer.register_client_accepted_message_type} method can
        register new message types accepted by this Landscape client.
        """
        self.broker.register_client_accepted_message_type("type1")
        self.broker.register_client_accepted_message_type("type2")
        self.assertEquals(self.exchanger.get_client_accepted_message_types(),
                          sorted(["type1", "type2"] + DEFAULT_ACCEPTED_TYPES))

    def test_fire_event(self):
        """
        The L{BrokerServer.fire_event} method fires an event in the broker
        reactor.
        """
        callback = self.mocker.mock()
        callback()
        self.mocker.replay()
        self.reactor.call_on("event", callback)
        self.broker.fire_event("event")

    def test_exit(self):
        """
        The L{BrokerServer.exit} method stops all registered clients.
        """
        self.broker.connectors_registry = {"foo": FakeCreator,
                                           "bar": FakeCreator}
        self.broker.register_client("foo")
        self.broker.register_client("bar")
        for client in self.broker.get_clients():
            client.exit = self.mocker.mock()
            self.expect(client.exit()).result(succeed(None))
        self.mocker.replay()
        return self.assertSuccess(self.broker.exit())

    def test_exit_exits_when_other_daemons_blow_up(self):
        """
        If a broker client blow up in its exit() methods, exit should ignore
        the error and exit anyway.
        """
        self.broker.connectors_registry = {"foo": FakeCreator}
        self.broker.register_client("foo")
        [client] = self.broker.get_clients()
        client.exit = self.mocker.mock()
        post_exit = self.mocker.mock()
        self.expect(client.exit()).result(fail(ZeroDivisionError()))
        post_exit()
        self.mocker.replay()
        self.reactor.call_on("post-exit", post_exit)

        def assert_event(ignored):
            self.reactor.advance(1)

        result = self.broker.exit()
        return result.addCallback(assert_event)

    def test_exit_fires_reactor_events(self):
        """
        The L{BrokerServer.exit} method fires a C{pre-exit} event before the
        clients are stopped and a C{post-exit} event after.
        """
        self.broker.connectors_registry = {"foo": FakeCreator}
        self.broker.register_client("foo")
        [client] = self.broker.get_clients()
        self.mocker.order()
        pre_exit = self.mocker.mock()
        client.exit = self.mocker.mock()
        post_exit = self.mocker.mock()
        pre_exit()
        self.expect(client.exit()).result(fail(ZeroDivisionError()))
        post_exit()
        self.mocker.replay()
        self.reactor.call_on("pre-exit", pre_exit)
        self.reactor.call_on("post-exit", post_exit)

        def assert_event(ignored):
            self.reactor.advance(1)

        result = self.broker.exit()
        return result.addCallback(assert_event)

    def test_listen_events(self):
        """
        The L{BrokerServer.listen_events} method returns a deferred which is
        fired when the first of the given events occurs.
        """
        result = self.broker.listen_events(["event1", "event2"])
        self.reactor.fire("event2")
        return self.assertSuccess(result, "event2")

    def test_listen_event_only_once(self):
        """
        The L{BrokerServer.listen_events} listens only to one occurrence of
        the given events.
        """
        result = self.broker.listen_events(["event"])
        self.assertEquals(self.reactor.fire("event"), [None])
        self.assertEquals(self.reactor.fire("event"), [])
        return self.assertSuccess(result, "event")


class EventTest(LandscapeTest):

    helpers = [RemoteClientHelper]

    def test_resynchronize(self):
        """
        The L{BrokerServer.resynchronize} method broadcasts a C{resynchronize}
        event to all connected clients.
        """
        callback = self.mocker.mock()
        self.expect(callback()).result("foo")
        self.mocker.replay()
        self.client_reactor.call_on("resynchronize", callback)
        return self.assertSuccess(self.broker.resynchronize(), [["foo"]])

    def test_impending_exchange(self):
        """
        The L{BrokerServer.impending_exchange} method broadcasts an
        C{impending-exchange} event to all connected clients.
        """
        plugin = self.mocker.mock()
        plugin.register(self.client)
        plugin.exchange()
        self.mocker.replay()
        self.client.add(plugin)
        return self.assertSuccess(self.broker.impending_exchange(), [[None]])

    def test_exchange_failed(self):
        """
        The L{BrokerServer.exchange_failed} method broadcasts an
        C{exchange-failed} event to all connected clients.
        """
        callback = self.mocker.mock()
        callback()
        self.mocker.replay()
        self.client_reactor.call_on("exchange-failed", callback)
        return self.assertSuccess(self.broker.exchange_failed(), [[None]])

    def test_registration_done(self):
        """
        The L{BrokerServer.registration_done} method broadcasts a
        C{registration-done} event to all connected clients.
        """
        callback = self.mocker.mock()
        callback()
        self.mocker.replay()
        self.client_reactor.call_on("registration-done", callback)
        return self.assertSuccess(self.broker.registration_done(), [[None]])

    def test_registration_failed(self):
        """
        The L{BrokerServer.registration_failed} method broadcasts a
        C{registration-failed} event to all connected clients.
        """
        callback = self.mocker.mock()
        callback()
        self.mocker.replay()
        self.client_reactor.call_on("registration-failed", callback)
        return self.assertSuccess(self.broker.registration_failed(), [[None]])

    def test_broker_started(self):
        """
        The L{BrokerServer.broker_started} method broadcasts a
        C{broker-started} event to all connected clients, which makes them
        re-registered any previously registered accepted message type.
        """

        def assert_broker_started(ignored):
            self.remote.register_client_accepted_message_type = \
                                                        self.mocker.mock()
            self.remote.register_client_accepted_message_type("type")
            self.remote.register_client = self.mocker.mock()
            self.remote.register_client("client")
            self.mocker.replay()
            return self.assertSuccess(self.broker.broker_reconnect(), [[None]])

        registered = self.client.register_message("type", lambda x: None)
        return registered.addCallback(assert_broker_started)

    def test_server_uuid_changed(self):
        """
        The L{BrokerServer.server_uuid_changed} method broadcasts a
        C{server-uuid-changed} event to all connected clients.
        """
        callback = self.mocker.mock()
        callback(None, "abc")
        self.mocker.replay()
        self.client_reactor.call_on("server-uuid-changed", callback)
        return self.assertSuccess(self.broker.server_uuid_changed(None, "abc"),
                                  [[None]])

    def test_message_type_acceptance_changed(self):
        """
        The L{BrokerServer.message_type_acceptance_changed} method broadcasts
        a C{message-type-acceptance-changed} event to all connected clients.
        """
        callback = self.mocker.mock()
        callback(True)
        self.mocker.replay()
        self.client_reactor.call_on(
            ("message-type-acceptance-changed", "type"), callback)
        result = self.broker.message_type_acceptance_changed("type", True)
        return self.assertSuccess(result, [[None]])

    def test_package_data_changed(self):
        """
        The L{BrokerServer.package_data_changed} method broadcasts a
        C{package-data-changed} event to all connected clients.
        """
        callback = self.mocker.mock()
        callback()
        self.mocker.replay()
        self.client_reactor.call_on("package-data-changed", callback)
        return self.assertSuccess(self.broker.package_data_changed(), [[None]])


class HandlersTest(LandscapeTest):

    helpers = [BrokerServerHelper]

    def setUp(self):
        super(HandlersTest, self).setUp()
        self.broker.connectors_registry = {"test": FakeCreator}
        self.broker.register_client("test")
        self.client = self.broker.get_client("test")

    def test_message(self):
        """
        The L{BrokerServer} calls the C{message} method on all
        registered plugins when messages are received from the server.
        """
        message = {"type": "foobar", "value": 42}
        self.client.message = self.mocker.mock()
        self.client.message(message)
        self.mocker.result(succeed(True))
        self.mocker.replay()
        self.transport.responses.append([{"type": "foobar", "value": 42}])
        self.exchanger.exchange()

    def test_message_failed_operation_without_plugins(self):
        """
        When there are no broker plugins available to handle a message, an
        operation-result message should be sent back to the server indicating a
        failure.
        """
        self.log_helper.ignore_errors("Nobody handled the foobar message.")
        self.mstore.set_accepted_types(["operation-result"])
        message = {"type": "foobar", "operation-id": 4}
        self.client.message = self.mocker.mock()
        self.client.message(message)
        self.mocker.result(succeed(False))
        self.mocker.replay()
        result = self.reactor.fire("message", message)
        result = [result for result in result if result is not None][0]

        class StartsWith(object):

            def __eq__(self, other):
                return other.startswith(
                    "Landscape client failed to handle this request (foobar)")

        def broadcasted(ignored):
            self.assertMessages(
                self.mstore.get_pending_messages(),
                [{"type": "operation-result", "status": FAILED,
                  "result-text": StartsWith(), "operation-id": 4}])

        result.addCallback(broadcasted)
        return result

    def test_impending_exchange(self):
        """
        When an C{impending-exchange} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = self.mocker.mock()
        self.client.fire_event("impending-exchange")
        self.mocker.result(succeed(None))
        self.mocker.replay()
        self.reactor.fire("impending-exchange")

    def test_exchange_failed(self):
        """
        When an C{exchange-failed} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = self.mocker.mock()
        self.client.fire_event("exchange-failed")
        self.mocker.result(succeed(None))
        self.mocker.replay()
        self.reactor.fire("exchange-failed")

    def test_registration_done(self):
        """
        When a C{registration-done} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = self.mocker.mock()
        self.client.fire_event("registration-done")
        self.mocker.result(succeed(None))
        self.mocker.replay()
        self.reactor.fire("registration-done")

    def test_message_type_acceptance_changed(self):
        """
        When a C{message-type-acceptance-changed} event is fired by the
        reactor, the broker broadcasts it to its clients.
        """
        self.client.fire_event = self.mocker.mock()
        self.client.fire_event("message-type-acceptance-changed", "test", True)
        self.mocker.result(succeed(None))
        self.mocker.replay()
        self.reactor.fire("message-type-acceptance-changed", "test", True)

    def test_server_uuid_changed(self):
        """
        When a C{server-uuid-changed} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = self.mocker.mock()
        self.client.fire_event("server-uuid-changed", None, 123)
        self.mocker.result(succeed(None))
        self.mocker.replay()
        self.reactor.fire("server-uuid-changed", None, 123)

    def test_package_data_changed(self):
        """
        When a C{package-data-changed} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = self.mocker.mock()
        self.client.fire_event("package-data-changed")
        self.mocker.result(succeed(None))
        self.mocker.replay()
        self.reactor.fire("package-data-changed")

    def test_resynchronize_clients(self):
        """
        When a C{resynchronize} event is fired by the reactor, the
        broker broadcasts it to its clients.
        """
        self.client.fire_event = self.mocker.mock()
        self.client.fire_event("resynchronize")
        self.mocker.result(succeed(None))
        self.mocker.replay()
        self.reactor.fire("resynchronize-clients")
