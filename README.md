# connchecky - a connection checker (client and server)

A python3 only connectivity checker that keeps notes.

Essentially, a client and server that reads a config file and then, using that,
either/and provides a server to send a reply (and timestamps that) or sends
requests expecting a reply (and timestamps that).  It records all the events
(and whether they were missed) to a log file.

Source code: https://github.com/openstack-charmers/connchecky

Bug reports: https://github.com/openstack-charmers/connchecky/issues

#### Execute Python Unit Tests

```
tox -e py3
```


#### Execute Python PEP-8 Tests
```
tox -e pep8
```

#### Build the Docs

```
tox -e docs
```
