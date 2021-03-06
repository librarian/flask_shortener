from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

from flask import Flask, render_template, send_file, send_from_directory, redirect, url_for, request
import redis
from redis.sentinel import Sentinel
import urlparse
import string
import os
from werkzeug.exceptions import HTTPException, NotFound
from math import floor

REDIS_PASSWORD=os.getenv('REDIS_PASSWORD', '')
REDIS_SENTINEL_PORT=os.getenv('REDIS_SENTINEL_PORT', '')
REDIS_SENTINELS=[ (host, REDIS_SENTINEL_PORT) for host in os.getenv('REDIS_SENTINELS', '').split(',') ]
REDIS_TIMEOUT=0.1

APP_PORT=os.getenv('APP_PORT', '8080')
APP_DOMAIN=os.getenv('APP_DOMAIN', 'clck.libc6.org')

sentinel = Sentinel(REDIS_SENTINELS, socket_timeout=REDIS_TIMEOUT, password=REDIS_PASSWORD)
master = sentinel.master_for('master', socket_timeout=REDIS_TIMEOUT)
slave = sentinel.slave_for('master', socket_timeout=REDIS_TIMEOUT)

app = Flask(__name__)
app.debug = True

def shorten(url):
        short_id = slave.get('reverse-url:' + url)
        if short_id is not None:
            return short_id
        url_num = master.incr('last-url-id')
        short_id = b62_encode(url_num)
        master.set('url-target:' + short_id, url)
        master.set('reverse-url:' + url, short_id)
        return short_id

def b62_encode(number):
    base = string.digits + string.lowercase + string.uppercase
    assert number >= 0, 'positive integer required'
    if number == 0:
        return '0'
    base62 = []
    while number != 0:
        number, i = divmod(number, 62)
        base62.append(base[i])
    return ''.join(reversed(base62))

@app.route('/', methods=["GET", "POST"])
def home():
    if request.method == 'GET':
        return render_template('index.html')
    elif request.method == 'POST':
        url_to_parse = request.form['input-url']
        parts = urlparse.urlparse(url_to_parse)
        if not parts.scheme in ('http', 'https'):
            error = "Please enter valid url"
        else:
            # with a valid url, shorten it using encode to 62
            short_id = shorten(url_to_parse)
        return render_template('result.html', short_id=short_id, app_domain=APP_DOMAIN)

@app.route("/<short_id>")
def expand_to_long_url(short_id):
    link_target = slave.get('url-target:' + short_id)
    if link_target is None:
        raise NotFound()
    return redirect(link_target)

http_server = HTTPServer(WSGIContainer(app))
http_server.listen(APP_PORT)
IOLoop.instance().start()
