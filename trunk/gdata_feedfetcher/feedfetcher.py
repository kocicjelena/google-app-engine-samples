# Copyright (C) 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


__author__ = 'api.jscudder (Jeffrey Scudder)'


import cgi
import wsgiref.handlers
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import urlfetch
import urllib # Used to unescape URL parameters.
import gdata.service
import gdata.urlfetch


gdata.service.http_request_handler = gdata.urlfetch


class StoredToken(db.Model):
  user_email = db.StringProperty(required=True)
  session_token = db.StringProperty(required=True)
  target_url = db.StringProperty(required=True)


class Fetcher(webapp.RequestHandler):

  def __init__(self):
    self.current_user = None
    self.feed_url = None
    self.token = None
    self.token_scope = None
    self.client = None
    self.show_xml = False

  def get(self):
    self.response.headers['Content-Type'] = 'text/html'

    self.current_user = users.GetCurrentUser()
    if self.current_user:
      self.response.out.write('<a href="%s">Sign Out</a>' % (
          users.CreateLogoutURL(self.request.uri)))
    else:
      self.response.out.write('<a href="%s">Sign In</a>' % (
          users.CreateLoginURL(self.request.uri)))
    self.response.out.write('</form></div>')

    for param in self.request.query.split('&'):
      if param.startswith('token_scope'):
        self.token_scope = urllib.unquote_plus(param.split('=')[1])
      elif param.startswith('token'):
        self.token = param.split('=')[1]
      elif param.startswith('feed_url'):
        self.feed_url = urllib.unquote_plus(param.split('=')[1])
      elif param.startswith('erase_tokens'):
        self.EraseStoredTokens()
      elif param.startswith('xml'):
        self.show_xml = True

    self.response.out.write("""<html><head>
         <title>Google Data Feed Fetcher: read Google Data API Atom feeds
         </title>
         <link rel="stylesheet" type="text/css" 
               href="static/feedfetcher.css"/>
         </head><body><div id="wrap"><div id="header">
         <form action="/" method="get">
         Target URL: <input type="text" size="60" name="feed_url" value="%s">
         </input><input type="submit" value="Fetch Atom"></input>
         Show XML:<input type="checkbox" name="xml" value="true" ></input>
         <a href="http://gdata-feedfetcher.appspot.com/">Home</a> """ % (
             self.feed_url or ''))
    

    # If we received a token for a specific feed_url and not a more general
    # scope, then use the exact feed_url in this request as the scope for the
    # token.
    if self.token and self.feed_url and not self.token_scope:
      self.token_scope = self.feed_url 

    self.ManageAuth()

    self.response.out.write('<div id="main">')
    if not self.feed_url:
      self.ShowInstructions()
    else:
      self.FetchFeed()
    self.response.out.write('</div>')

    if self.current_user:
      self.response.out.write("""<div id="sidebar"><div id="scopes">
          <h4>Request a token for some common scopes</h4><ul>
          <li><a href="%s">Blogger</a></li>
          <li><a href="%s">Calendar</a></li>
          <li><a href="%s">Google Documents</a></li>
          </ul></div><br/><div id="tokens">""" % (
              self.GenerateScopeRequestLink('http://www.blogger.com/feeds/'),
              self.GenerateScopeRequestLink(
                  'http://www.google.com/calendar/feeds'),
              self.GenerateScopeRequestLink(
                  'http://docs.google.com/feeds/')))

      self.DisplayAuthorizedUrls()
      self.response.out.write('</div>')
    self.response.out.write('</div></div></body></html>')
    
  def GenerateScopeRequestLink(self, scope):
    return self.client.GenerateAuthSubURL(
        'http://gdata-feedfetcher.appspot.com/?token_scope=%s' % (scope),
        scope, secure=False, session=True)

  def ShowInstructions(self):
    self.response.out.write("""<p>This sample application illustrates the
        use of <a 
        href="http://code.google.com/apis/accounts/docs/AuthForWebApps.html">
        AuthSub authentication</a> to access 
        <a href="http://code.google.com/apis/gdata/">Google Data feeds</a>.</p>

        <p>To start using this sample, you can enter the URL for an Atom feed
        or entry in the input box above, or you can click on one of the 
        example feeds below. Some of these feeds require you to authorize this
        app to have access. To avoid authorizing over and over, sign in to
        this application above and previous authorization tokens will be stored
        for future use.</p>

        <h4>Sample Feed URLs</h4>
        <h5>Publicly viewable feeds</h5>
        <a href="http://gdata-feedfetcher.appspot.com/?feed_url=%s"
        >Recent posts in the Google Data APIs blog</a><br/>
        <h5>Feeds which require authorization</h5>
        <a href="http://gdata-feedfetcher.appspot.com/?feed_url=%s"
        >List your Google Documents</a><br/>
        <a href="http://gdata-feedfetcher.appspot.com/?feed_url=%s"
        >List the Google Calendars that you own</a><br/>
        <a href="http://gdata-feedfetcher.appspot.com/?feed_url=%s"
        >List your Google Calendars</a><br/>
        <a href="http://gdata-feedfetcher.appspot.com/?feed_url=%s"
        >List your blogs on Blogger</a><br/>
        

        <p>In addition to reading information in Google Data feeds, 
        it is also possible to write to some of the Google Data services
        once the user has granted permission to your app. For more details
        on the capabilities of the different Google Data service see the
        <a href="http://code.google.com/apis/gdata/">home page</a> for 
        Google Data APIs.</p>

        <p>This app uses the <a 
        href="http://code.google.com/p/gdata-python-client/"
        >gdata-python-client</a> library.</p>
    """ % ('http://www.blogger.com/feeds/32786009/posts/default',
        'http://docs.google.com/feeds/documents/private/full', 
        'http://www.google.com/calendar/feeds/default/owncalendars/full',
        'http://www.google.com/calendar/feeds/default/allcalendars/full',
        'http://www.blogger.com/feeds/default/blogs'))

  def ManageAuth(self):
    self.client = gdata.service.GDataService()
    if self.token and self.current_user:
      # Upgrade to a session token and store the session token in the data
      # store.
      self.UpgradeAndStoreToken()
    elif self.token:
      # Use the token to make the request, but do not store it sine there is
      # no user to associate with the session token.
      self.client.auth_token = self.token
    elif self.current_user:
      # Try to lookup the token for this user and this feed_url, and fetch
      # using a shared session token.
      self.LookupToken()
    else:
      # Try to fetch the feed without using an authorization header.
      pass
      
  def FetchFeed(self):
    # Attempt to fetch the feed.
    if not self.client:
      self.client = gdata.service.GDataService()
    try:
      feed = self.client.Get(self.feed_url, converter=str)
      self.response.out.write(cgi.escape(feed))
    except gdata.service.RequestError, request_error:
      # If fetching fails, then tell the user that they need to login to
      # authorize this app by logging in at the following URL.
      if request_error[0]['status'] == 401:
        # Get the URL of the current page so that our AuthSub request will
        # send the user back to here.
        next = self.request.uri
        auth_sub_url = self.client.GenerateAuthSubURL(next, self.feed_url,
            secure=False, session=True)
        self.response.out.write('<a href="%s">' % (auth_sub_url))
        self.response.out.write(
            'Click here to authorize this application to view the feed</a>')
      else:
        self.response.out.write(
            'Something else went wrong, here is the error object: %s ' % (
                str(request_error[0])))

    
  def UpgradeAndStoreToken(self):
    self.client.auth_token = self.token
    self.client.UpgradeToSessionToken()
    # Create a new token object for the data store which associates the
    # session token with the requested URL and the current user.
    if self.token_scope:
      new_token = StoredToken(user_email=self.current_user.email(),
          session_token=self.client.auth_token, target_url=self.token_scope)
    else:
      new_token = StoredToken(user_email=self.current_user.email(), 
          session_token=self.client.auth_token, target_url=self.feed_url)
    new_token.put()

  def LookupToken(self):
    if self.feed_url:
      stored_tokens = StoredToken.gql('WHERE user_email = :1', 
          self.current_user.email())
      for token in stored_tokens:
        if self.feed_url.startswith(token.target_url):
          self.client.auth_token = token.session_token
          return

  def DisplayAuthorizedUrls(self):
    self.response.out.write('<h4>Stored Authorization Tokens</h4><ul>')
    delete_stored_tokens_url = self.request.uri
    if delete_stored_tokens_url.find('erase_tokens=true') < 0:
      if delete_stored_tokens_url.find('?') > -1:
        delete_stored_tokens_url += '&erase_tokens=true'
      else:
        delete_stored_tokens_url += '?erase_tokens=true'
    stored_tokens = StoredToken.gql('WHERE user_email = :1', 
        self.current_user.email())
    for token in stored_tokens:
        self.response.out.write('<li><a href="/?feed_url=%s">%s*</a></li>' % (
            urllib.quote_plus(token.target_url), token.target_url))
    self.response.out.write(
        '</ul>To erase your stored tokens, <a href="%s">click here</a>' % (
            delete_stored_tokens_url))

  def EraseStoredTokens(self):
    if self.current_user:
      stored_tokens = StoredToken.gql('WHERE user_email = :1',
          self.current_user.email())
      for token in stored_tokens:
        token.delete()


class Acker(webapp.RequestHandler):
  """Simulates an HTML page to prove ownership of this domain for AuthSub 
  registration."""

  def get(self):
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.out.write('This file present for AuthSub registration.')


def main():
  application = webapp.WSGIApplication([('/', Fetcher), ('/google72db3d6838b4c438.html', Acker)], debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()