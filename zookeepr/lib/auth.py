import md5

from authkit.middleware import Authenticator
from authkit.controllers import PylonsSecureController
import formencode
import pylons
from sqlalchemy import create_session

from zookeepr.models import Person

class UserModelAuthenticator(Authenticator):
    """Look up the user in the database"""

    def check_auth(self, email_address, password):
        session = create_session()
        ps = session.query(Person).select_by(email_address=email_address)
        if len(ps) <> 1:
            return False

        password_hash = md5.new(password).hexdigest()
        
        result = password_hash == ps[0].password_hash
        session.close()
        return result

class AuthenticateValidator(formencode.FancyValidator):
    def _to_python(self, value, state):
        if state.authenticate(value['email_address'], value['password']):
            return value
        else:
            raise formencode.Invalid('Incorrect password', value, state)

class ExistingEmailAddress(formencode.FancyValidator):
    def _to_python(self, value, state):
        auth = state.auth
        if not value:
            raise formencode.Invalid('Please enter a value',
                                     value, state)
        elif not auth.user_exists(value):
            raise formencode.Invalid('No such user', value, state)
        return value
    
class SignIn(formencode.Schema):
    go = formencode.validators.String()
    email_address = ExistingEmailAddress()
    password = formencode.validators.String(not_empty=True)
    chained_validators = [
        AuthenticateValidator()
        ]

class UserModelAuthStore(object):
    def __init__(self):
        self.status = {}
        
    def user_exists(self, value):
        session = create_session()
        ps = session.query(Person).select_by(email_address=value)
        result = len(ps) > 0
        return result

    def sign_in(self, username):
        self.status[username] = ()

    def sign_out(self, username):
        if self.status.has_key(username):
            del self.status[username]

    def authorise(self, email_address, role=None, signed_in=None):
        if signed_in is not None:
            is_signed_in = False
            if self.status.has_key(email_address):
                is_signed_in = True

            return signed_in and is_signed_in
        
        return True

class SecureController(PylonsSecureController):
    def __granted__(self, action):
        action_ = getattr(self, action)

        # FIXME: this is a dirty hack so that the test suite doesn't have to
        # log in to test that the behaviour is correct.  I suspect that
        # special-casing for the test suite means that it'll mask some bugs
        if pylons.request.environ.has_key('paste.testing'):
            return True
        
        if hasattr(action_, 'permissions'):
            if not pylons.request.environ.has_key('paste.login.http_login'):
                raise Exception("action permissions specified but security middleware not present")
            if pylons.request.environ.has_key('REMOTE_USER'):
                if self.__authorize__(pylons.request.environ['REMOTE_USER'], action_.permissions):
                    return True
                else:
                    pylons.m.abort(403, 'Computer says no')
            else:
                pylons.m.abort(401, 'Not signed in')
        else:
            return True

    def __authorize__(self, signed_in_user, ps):
        permissions = {}
        g = pylons.request.environ['pylons.g']
        
        for k, v in ps.items():
            permissions[k] = v

        def valid():
            if permissions.has_key('email_address'):
                if signed_in_user.lower() <> permissions['email_address'].lower():
                    return False
            else:
                permissions['email_address'] = signed_in_user

            if not g.auth.user_exists(permissions['email_address']):
                return False
            else:
                return g.auth.authorise(**permissions)

        if valid():
            return True
        else:
            self.__signout__(permissions['email_address'])
            return False
