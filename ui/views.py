"""
Views for Indivo JS UI
"""

# todo: rm unused
from django.http import HttpResponse, HttpResponseRedirect, Http404, HttpResponseForbidden, HttpRequest
from django.contrib.auth.models import User
from django.core.exceptions import *
from django.core.urlresolvers import reverse
from django.core import serializers
from django.db import transaction
from django.conf import settings
from django.utils import simplejson
from indivo_client_py.oauth import oauth
import xml.etree.ElementTree as ET
import urllib, re
import httplib, urllib, urllib2, urlparse
import time
import utils
HTTP_METHOD_GET = 'GET'
HTTP_METHOD_POST = 'POST'
LOGIN_PAGE = 'ui/login'
DEBUG = True

# init the IndivoClient python object
from indivo_client_py.lib.client import IndivoClient

SMART_SERVER_LOCATION = urlparse.urlparse(settings.SMART_API_SERVER_BASE)
SMART_SERVER_LOCATION = {
  'host':SMART_SERVER_LOCATION.hostname,
  'scheme': SMART_SERVER_LOCATION.scheme,
  'port': SMART_SERVER_LOCATION.port or (
    SMART_SERVER_LOCATION.scheme=='http' and '80' or 
    SMART_SERVER_LOCATION.scheme=='https' and '443')
  }


def get_api(request=None):
  api = IndivoClient(settings.CONSUMER_KEY, settings.CONSUMER_SECRET, SMART_SERVER_LOCATION)
  if request:
    api.update_token(request.session['oauth_token_set'])
  
  return api
def tokens_p(request):
  try:
    if request.session['oauth_token_set']:
      return True
    else:
      return False
  except KeyError:
    return False

def tokens_get_from_server(request, username, password):
  # aks - hack! re-init IndivoClient here
  api = get_api()
  tmp = api.create_session({'username' : username, 'user_pass' : password})
  
  if not tmp and DEBUG:
    utils.log('error: likely a bad username/password, or incorrect tokens from UI server to backend server.')
    return False
  
  request.session['username'] = username
  request.session['oauth_token_set'] = tmp
  request.session['account_id'] = urllib.unquote(tmp['account_id'])
  
  if DEBUG:
    utils.log('oauth_token: %(oauth_token)s outh_token_secret: %(oauth_token_secret)s' %
             request.session['oauth_token_set'])
  
  return True

def proxy_index(request):
   api = get_api()

   record_id = request.GET['record_id']
   record_name = request.GET.get('record_name', "Proxied Patient")
   initial_app= request.GET.get('initial_app', "")

   api.call("POST", "/records/create/proxied", options={
       'data': {'record_id':record_id, 
                'record_name':record_name,
                }
       })

   options = {}
   pin= request.GET.get('pin', "")   
   if pin: 
     options['data'] = {'pin' : pin}

   base = "/records/%s/generate_direct_url" 
   target_url = api.call("GET", base%record_id, options=options)
   
   if initial_app != "":
     target_url += "?initial_app="+initial_app

   return HttpResponseRedirect(target_url)

def token_login_index(request, token):
   request.session.flush()
   api = get_api()

   reqstore = request.GET
   if (request.method == 'POST'): reqstore = request.POST
    
   initial_app= reqstore.get('initial_app', "")

   options = {'data': {'token':token}}
   pin= reqstore.get('pin', "")   
   if pin: 
     options['data']['pin'] = pin

   logintokenxml =   api.call("GET", "/session/from_direct_url", 
                              options=options)

   if logintokenxml.startswith("Permission Denied"):
       if "Wrong pin" in logintokenxml:
          return utils.render_template("ui/need_pin",{})
       return HttpResponse(logintokenxml)

   logintoken= ET.fromstring(logintokenxml) 
   record_id = logintoken.find("Record").get("id")
   record_name = logintoken.find("Record").get("label")

   session_tokens = dict(urlparse.parse_qsl(logintoken.get("value")))
   account_id = session_tokens['account_id']
   request.session['oauth_token_set'] = session_tokens
   request.session['account_id'] = urllib.unquote(account_id)

   api = get_api(request)
   account_id = urllib.unquote(request.session['oauth_token_set']['account_id'])
   ret = api.account_info(account_id = account_id)

   e = ET.fromstring(ret.response['response_data'])
   fullname = e.findtext('givenName') +" "+ e.findtext('familyName')

   target_template = "ui/proxy_index"


   credentials = "''"
   manifest = "''"

   if (initial_app != ""):
     target_template = "ui/single_app_view"
     credentials = single_app_get_credentials(api, account_id, initial_app, record_id)
     manifest = single_app_get_manifest(api, initial_app)

   return utils.render_template(target_template,
         { 
         'ACCOUNT_ID': session_tokens["account_id"],
         'FULLNAME': fullname,
         'PROXIED_RECORD_ID' : record_id,
         'PROXIED_RECORD_NAME': record_name,
         'INITIAL_APP': initial_app,
         'SMART_PASSTHROUGH_SERVER': passthrough_server ,
         'CREDENTIALS': credentials,
         'MANIFEST': manifest 
         })

def single_app_get_manifest(api, app_id):
  r =  api.call("GET", "/apps/%s/manifest"%app_id)
  return r


def single_app_get_credentials(api, account_id, app_id, record_id=None):
    launch_opts = {}

    if record_id:
      launch_opts['record_id'] = record_id

    launchdata = api.call("GET", 
                          "/accounts/%s/apps/%s/launch"%(account_id, app_id), 
                          options = { 'data': launch_opts })
    
    e = ET.fromstring(launchdata)
    credentials = {
        	    "connect_token":  e.findtext('ConnectToken'), 
        	    "connect_secret":e.findtext('ConnectSecret'), 
		    "api_base": e.findtext('APIBase'), 
		    "rest_token":e.findtext('RESTToken'),  
		    "rest_secret": e.findtext('RESTSecret'), 
        	    "oauth_header": e.findtext('OAuthHeader')
		}; 

    return simplejson.dumps(credentials)

def showcase_index(request):
   api = get_api()

   initial_app= request.GET.get('initial_app', "")

   ret = tokens_get_from_server(request, settings.PROXY_USER, settings.PROXY_PASSWORD)
   if not ret:
     return utils.render_template(LOGIN_PAGE, {'error': 'Could not find proxied user'})

   return utils.render_template('ui/showcase',
          { 'ACCOUNT_ID': settings.PROXY_USER,
            'INITIAL_APP': initial_app,
            'SMART_PASSTHROUGH_SERVER': passthrough_server })


def mobile_index(request, template='ui/mobile_index'):
  return index(request,  template)

   
def index(request, template='ui/index'):
  print "INDEX", template

  if tokens_p(request):
    # get the realname here. we already have it in the js account model
    try:
        api = get_api(request)
        account_id = urllib.unquote(request.session['oauth_token_set']['account_id'])
        ret = api.account_info(account_id = account_id)
        e = ET.fromstring(ret.response['response_data'])
        
        fullname = e.findtext('givenName') +" "+ e.findtext('familyName')
        return utils.render_template(template,
          { 'ACCOUNT_ID': account_id,
            'FULLNAME': fullname,
            'HIDE_GET_MORE_APPS': settings.HIDE_GET_MORE_APPS,
            'SMART_PASSTHROUGH_SERVER': passthrough_server })
    except:  pass

  if (template == "ui/mobile_index"):
    return HttpResponseRedirect(reverse(mobile_login))
  return HttpResponseRedirect(reverse(login))

def launch_app(request, account_id, pha_email):
    if not tokens_p(request):
      return HttpResponseRedirect(reverse(login))

    api = get_api(request)

    record_id = request.GET.get('record_id', None)
    launch_opts = {}

    if record_id:
      launch_opts['record_id'] = record_id

    launchdata = api.call("GET", 
                          "/accounts/%s/apps/%s/launch"%(account_id, pha_email), 
                          options = { 'data': launch_opts })
    
    return HttpResponse(launchdata)

def smart_passthrough(request):
  if not tokens_p(request):
    return HttpResponseForbidden()

  relative_path =  request.get_full_path().replace(passthrough_server, "")
  full_path = api_server() + relative_path

  query_string = request.META['QUERY_STRING']
  body = request.raw_post_data
  data = query_string or body

  content_type = request.META['CONTENT_TYPE']
  method = request.method

  http_request = oauth.HTTPRequest(method=method, 
                                   path=full_path, 
                                   data=data,
                                   data_content_type=content_type)  

  c = oauth.parse_header(request.META['HTTP_AUTHORIZATION'])
  token_str =  c['smart_connect_token']
  secret =  c['smart_connect_secret']

  token = oauth.OAuthToken(token= token_str, 
                           secret =secret)

  consumer = oauth.OAuthConsumer(consumer_key = settings.CONSUMER_KEY, 
                                 secret = settings.CONSUMER_SECRET)
  
  oauth_request = oauth.OAuthRequest(consumer, 
                                     token, 
                                     http_request)
  
  oauth_request.sign()

  headers = oauth_request.to_header(with_content_type=True)
  api = api_server(include_scheme=False)

  if request.is_secure():
    conn = httplib.HTTPSConnection(api)
  else:
    conn = httplib.HTTPConnection(api)
    
  conn.request(request.method, full_path.split(api)[1], body, headers)
  r = conn.getresponse()    
  data = r.read()
  conn.close()
  
  ret = HttpResponse(data, 
                     content_type=r.getheader("Content-type"), 
                     status=r.status)

  ret['Expires'] = "Sun, 19 Nov 1978 05:00:00 GMT"
  ret['Last-Modified'] =  time.ctime()
  ret['Cache-Control'] = "store, no-cache, must-revalidate, post-check=0, pre-check=0" 
  return ret

def api_server(include_scheme = True):
    loc = SMART_SERVER_LOCATION
    port = loc['port']
    scheme=loc['scheme']
    host = loc['host']

    port_matches = (scheme=='http' and port=='80') or (scheme=='https'  and port=='443')

    if (port_matches):
      ret = host
    else:
      ret =  "%s:%s"%(host, port )

    if (include_scheme):
      return "%s://%s"%(scheme, ret)
    return ret

passthrough_server = "/smart_passthrough"

def mobile_login(request, info="", template='ui/mobile_login'):
  return login(request, info, template)
  
def login(request, info="", template=LOGIN_PAGE):
  """
  clear tokens in session, show a login form, get tokens from indivo_server, then redirect to index
  FIXME: make note that account will be disabled after 3 failed logins!!!
  """
  # generate a new session
  request.session.flush()
  
  # set up the template
  errors = {'missing': 'Either the username or password is missing. Please try again',
            'incorrect' : 'Incorrect username or password.  Please try again.',
            'disabled' : 'This account has been disabled/locked.'}
  
  FORM_USERNAME = 'username'
  FORM_PASSWORD = 'password'
  FORM_RETURN_URL = 'return_url'
  
  # process form vars
  if request.method == HTTP_METHOD_GET:
    return_url = request.GET.get(FORM_RETURN_URL, '/')
    if (return_url.strip()==""): return_url='/'
    template_data = {FORM_RETURN_URL: return_url}

    return utils.render_template(template, 
                                 template_data
                                 )
  
  if request.method == HTTP_METHOD_POST:
    return_url = request.POST.get(FORM_RETURN_URL, '/')
    if (return_url.strip()==""): return_url='/'
    if request.POST.has_key(FORM_USERNAME) and request.POST.has_key(FORM_PASSWORD):
      username = request.POST[FORM_USERNAME]
      password = request.POST[FORM_PASSWORD]
    else:
      # Also checked initially in js
      return utils.render_template(template, {'error': errors['missing'], FORM_RETURN_URL: return_url})
  else:
    utils.log('error: bad http request method in login. redirecting to /')
    return HttpResponseRedirect('/')
  
  # get tokens from the backend server and save in this user's django session
  ret = tokens_get_from_server(request, username, password)
  if not ret:
    return utils.render_template(LOGIN_PAGE, {'error': errors['incorrect'], FORM_RETURN_URL: return_url})
  return HttpResponseRedirect(return_url)

def logout(request):
  # todo: have a "you have logged out message"
  request.session.flush()
  return HttpResponseRedirect('/login')

def account_initialization(request):
  """
  http://localhost/indivoapi/accounts/foo@bar.com/initialize/icmloNHxQrnCQKNn
  """
  errors = {'generic': 'There was a problem setting up your account. Please try again.'}
  api = IndivoClient(settings.CONSUMER_KEY, settings.CONSUMER_SECRET, SMART_SERVER_LOCATION)
  
  if request.method == HTTP_METHOD_GET:
    return utils.render_template('ui/account_init', {})
  
  if request.method == HTTP_METHOD_POST:
    # a 404 returned from this call could indicate that the account doesn't exist! Awesome REST logic!
    account_id = request.path_info.split('/')[3]
    ret = api.account_initialize(account_id = account_id,
                                 primary_secret = request.path_info.split('/')[5],
                                 data = {'secondary_secret':request.POST['conf1'] + request.POST['conf2']})
    
    if ret.response['response_status'] == 200:
      return utils.render_template('ui/account_init_2', {'FULLNAME': ''})
    else:
      return utils.render_template('ui/account_init', {'ERROR': errors['generic']})

def account_initialization_2(request):
  if request.method == HTTP_METHOD_POST:
    account_id = request.path_info.split('/')[3]
    username = request.POST['username']
    password = request.POST['pw1']
    errors = {'generic': 'There was a problem updating your data. Please try again. If you are unable to set up your account please contact support.'}
    api = IndivoClient(settings.CONSUMER_KEY, settings.CONSUMER_SECRET, SMART_SERVER_LOCATION)
    ret = api.add_auth_system(
      account_id = account_id,
      data = {'system':'password',
              'username': username,
              'password': password}
    )
    
    if ret.response['response_status'] == 200:
      # everything's OK, log this person in, hard redirect to change location
      tokens_get_from_server(request, username, password)
      return HttpResponseRedirect('/')
    else:
      return utils.render_template('ui/account_init_2', {'ERROR': errors['generic']})
  else:
    return utils.render_template('ui/account_init_2', {})

def indivo_api_call_get(request):
  """
  take the call, forward it to the Indivo server with oAuth signature using
  the session-stored oAuth tokens
  """
  if DEBUG:
    utils.log('indivo_api_call_get: ' + request.path)
  
  if not tokens_p(request):
    utils.log('indivo_api_call_get: No oauth_token or oauth_token_secret.. sending to login')
    return HttpResponseRedirect('/login')
  
  # update the IndivoClient object with the tokens stored in the django session
  api = get_api(request)
  
  # strip the leading /indivoapi, do API call, and return result
  if request.method == "POST":
    data = dict((k,v) for k,v in request.POST.iteritems())
  elif request.method == "GET":
    data = dict((k,v) for k,v in request.GET.iteritems())
  else:
    data = {}
  ret = HttpResponse(api.call(request.method, request.path[10:], options= {'data': data}), mimetype="application/xml")
  return ret

def indivo_api_call_delete_record_app(request):
  """
  sort of like above but for app delete
  """
  if request.method != HTTP_METHOD_POST:
    return HttpResponseRedirect('/')
  
  if DEBUG:
    utils.log('indivo_api_call_delete_record_app: ' + request.path + ' ' + request.POST['app_id'] + ' ' + request.POST['record_id'])
  
  if not tokens_p(request):
    utils.log('indivo_api_call_delete_record_app: No oauth_token or oauth_token_secret.. sending to login')
    return HttpResponseRedirect('/login')
  
  # update the IndivoClient object with the tokens stored in the django session
  api = get_api(request)
  
  # get the app id from the post, and return to main
  status = api.delete_record_app(record_id=request.POST['record_id'],app_id=request.POST['app_id']).response['response_status']
  
  return HttpResponse(str(status))

def authorize(request):
  # check user is logged in
  if not tokens_p(request):
    url = "%s?return_url=%s" % (reverse(login), urllib.quote(request.get_full_path()))
    return HttpResponseRedirect(url)
  
  api = get_api(request)
  
  # read the app info
  REQUEST_TOKEN = request.REQUEST['oauth_token']
  
  # process GETs (initial adding and a normal call for this app)
  if request.method == HTTP_METHOD_GET and request.GET.has_key('oauth_token'):
    # claim request token and check return value
    if api.claim_request_token(request_token=REQUEST_TOKEN).response['response_status'] != 200:
      return HttpResponse('bad response to claim_request_token')
    app_info = api.get_request_token_info(request_token=REQUEST_TOKEN).response['response_data']
    e = ET.fromstring(app_info)

    record_id = e.find('record').attrib.get('id', None)

    name = e.findtext('App/name')
    app_id = e.find('App').attrib['id']
    kind = e.findtext('kind')
    description = e.findtext('App/description')
    
    offline_capable = (e.findtext('DataUsageAgreement/offline') == "1")
 
    # the "kind" param lets us know if this is app setup or a normal call
    if kind == 'new':     
      return utils.render_template('ui/authorize',
          {'NAME': name, 'DESCRIPTION': description, 'REQUEST_TOKEN': REQUEST_TOKEN, 'offline_capable' : offline_capable})
    elif kind == 'same':
      # return HttpResponse('fixme: kind==same not implimented yet')
      # in this case we will have record_id in the app_info
      return _approve_and_redirect(request, REQUEST_TOKEN)
    else:
      return HttpResponse('bad value for kind parameter')
  
  # process POST
  elif request.method == HTTP_METHOD_POST \
    and request.POST.has_key('oauth_token'):
    
    app_info = api.get_request_token_info(request_token=REQUEST_TOKEN).response['response_data']
    e = ET.fromstring(app_info)
    
    name = e.findtext('App/name')
    app_id = e.find('App').attrib['id']
    kind = e.findtext('kind')
    description = e.findtext('App/description')
    
    offline_capable = request.POST.get('offline_capable', False)
    if offline_capable == "0":
      offline_capable = False
        
    return _approve_and_redirect(request, request.POST['oauth_token'],  offline_capable = offline_capable)
  else:
    return HttpResponse('bad request method or missing param in request to authorize')

def _approve_and_redirect(request, request_token, account_id=None,  offline_capable=False):
  """
  carenet_id is the carenet that an access token is limited to.
  """
  api = get_api(request)
  data = {}
    
  if offline_capable:
    data['offline'] = 1
  
  result = api.approve_request_token(request_token=request_token, data=data)
  # strip location= (note: has token and verifer)
  location = urllib.unquote(result.response['prd'][9:])
  
  return HttpResponseRedirect(location)

def create_developer_account(request):
  if request.method == "GET":
    return utils.render_template('ui/create_developer_account',
      {})
    

  api = get_api()

  username = request.POST.get("username")
  password = request.POST.get("password")
  given_name = request.POST.get("given_name")
  family_name = request.POST.get("family_name")
  department = request.POST.get("department")
  role = request.POST.get("role")

  data = {"account_id" : username, "password" : password, 
          "given_name" : given_name, "family_name" : family_name, 
          "department": department, "role" : role}

  ret = api.call("POST", "/users/", options={'data': data})
  if (ret == "account_exists"):
    return utils.render_template('ui/create_developer_account',
      { 'error': "Account '%s' is already registered."%username })
  

  return utils.render_template(LOGIN_PAGE, 
                                 {"error": "Account %s has been created.  Please log in."%username,
                                  "account" : username
                                  }
                                 )

def reset_password_request(request):
  if request.method == "GET":
    return utils.render_template('ui/reset_password_request', {})

  account_email = request.POST.get("account_email")
  data = {"account_email" : account_email}

  api = get_api()
  ret = api.call("POST", "/users/reset_password_request", options={'data': data})
  if (ret == "no_account_exists"):
    return utils.render_template('ui/reset_password_request',
      { 'error': "Account '%s' does not exist."%account_email})

  
  return utils.render_template(LOGIN_PAGE, 
                              {"error": "Account reset link e-mailed. Please check your e-mail for the link.",
                              "account" : account_email})
     
def reset_password(request):
  if request.method == "GET":
      account=request.GET.get('account_email', None)
      secret=request.GET.get('account_secret', None)
      return utils.render_template('ui/reset_password', {'account_email': account, 'account_secret': secret})
  

  account_email = request.POST.get('account_email', None)
  data = {"account_email" : account_email,
          "account_secret": request.POST.get('account_secret', None),
          "new_password": request.POST.get('new_password', None)}

  
  api = get_api()
  ret = api.call("POST", "/users/reset_password", options={'data': data})
  
  return utils.render_template(LOGIN_PAGE, 
                              {"error": "Account password has been reset. Please log in below.",
                              "account" : account_email})
