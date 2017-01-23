# Corotwine

Corotwine is an interface to various Twisted APIs using greenlet.

The latest release is available at http://launchpad.net/corotwine. The release notes are available at https://launchpad.net/corotwine/+announcements.


## Status

I never really did much on this library after I designed and implemented it during a weekend in March of 2008. I have no idea if it still works. However, I will accept pull requests if they are tested and documented. Please contact me if you want to take on maintenance.

## Dependencies

 * Twisted >= 8.1 (Ubuntu 'python-twisted', http://twistedmatrix.com/)
 * greenlet

## Learning

There are examples in corotwine/examples.py.

There is API documentation at
http://twistedmatrix.com/users/radix/corotwine/api/

Currently there are three interesting systems:

 * Protocol support at corotwine.protocol. Write TCP servers and clients.
 * Deferred support at corotwine.defer. Integrate with Deferred-using code    in both directions.
 * Time support at corotwine.clock.


## Contributing

If you'd like to make contributions, please make sure they're unit-tested and documented, and submit a Pull Request.
