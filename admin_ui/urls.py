from django.conf.urls.defaults import *
from django.conf import settings
from admin_ui.views import *

urlpatterns = patterns('',
    (r'^$', index),
    (r'^login$', login),
    (r'^logout$', logout),
    (r'^add$', manifest_add),
    (r'^manifest/(?P<app_id>.+)$', manifest_get),
    (r'^delete$', manifest_delete),
    (r'^static/(?P<path>.*)$', 'django.views.static.serve', {'document_root': settings.APP_HOME + '/admin_ui/static'}),
)
