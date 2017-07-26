naumanni no server


## Development

### Install Prerequisites

```
$ brew install redis
```

### Launch daemons

```
# Ensure redis-server is launched
$ redis-server /usr/local/etc/redis.conf
```

### Locate config.py

<p>
<details>
    <summary>/path/to/naumanni-server/config.py</summary>

```
listen = (8888,)
redis = '127.0.0.1', 6379, 7
```
</details>

---

## Activate Plugins

### Activate virtualenv of naumanni-server

```
$ cd /path/to/naumanni-server
$ . .env/bin/activate
```

### Activate Plugin

```
# Ensure you're in virtualenv of naumanni-server
(.env)$ cd /path/to/naumanni-plugin
(.env)$ python setup.py develop
```

### Link Plugin

```
$ ln -s /path/to/naumanni/node_modules/ .
$ yarn link
```

---

### Setup naumanni-server

```
$ python3.6 -m venv .env
$ . .env/bin/activate
(.env)$ pip install -e '.[test]'
(.env)$ python setup.py develop
(.env)$ naumanni --debug webserver

# test
$ curl http://localhost:8888/ping
```

### Install Plugins

* Generate plugin assets & locate to naumanni client directory

```
(.env)$ naumanni gen js > /path/to/naumanni/plugin_entries.es6
(.env)$ naumanni gen css > /path/to/naumanni/plugin_entries.css
```

* Locate config.es6

<p>
<details>
    <summary>/path/to/naumanni/config.es6</summary>

```
/**
 * With this file, you can change the behavior of Naumanni.
 * You can set up the screen the user first sees and guide user to your own instance.
 */

export default {
  // Set If you have your Mastodon instance. The new registration button will be displayed in the Welcome dialog.
  PREFERRED_INSTANCE: 'mastodon.super.heros',

  PROXY_ENABLED: true,

  WELCOME_DIALOG: {
    // CSS of the welcome dialog
    dialogStyle: {
      background: '#F0F3F5',
    },

    // content of the welcome dialog
    html: `\
<style type="text/css">
  .welcome-note {
    padding: 8px;
    min-height: 256px;
  }
  .welcome-note .logo {
    display: block;
    width: 256px;
    float: right;
  }
  .welcome-note h3 {
    color: #066399;
    margin: 0 0 1ex;
  }
</style>

<img class="logo" src="/static/images/naumanni-logo.svg" />
<h3>What is mastodon.super.heros?</h3>
<p>blah blah blah</p>
`,
  },
}
```
</details>

* Build

```
$ cd /path/to/naumanni
$ yarn link <naumanni-plugin-name>
$ yarn run build
```

<details>
<summary> Run(nginx example) </summary>

#### Project tree

```
.
├── README.md
├── coverage
│   ├── clover.xml
│   ├── coverage-final.json
│   ├── lcov-report
│   └── lcov.info
├── etc
│   └── s3cmd_maintenance.sh
│   ├── deploy.sh
│   ├── deploy_s3_alpha.sh
│   ├── dev
│   │   ├── logs
│   │   │   └── access.log
│   │   ├── nginx
│   │   │   ├── mime.types
│   │   │   ├── nginx.conf
│   │   │   └── uwsgi_params
│   │   ├── nginx.pid
│   │   └── tmp
│   │       └── client_tmp
├── dev.screenrc
├── exclude-files
└── s3cmd_maintenance.sh
├── node_modules
│   ├── ***
├── package.json
├── postcss.config.js
├── raw
│   ├── copy-fonts.sh
│   └── fontello-c1112e15
├── src
│   ├── css
│   └── js
├── static
│   ├── font
│   ├── images
│   ├── main.bundle.js
│   ├── main.bundle.js.map
│   └── main.css
├── webpack.config.babel.js
├── www
│   ├── authorize
│   ├── favicon.ico
│   └── index.html
└── yarn.lock
```

<p>
<details>
<summary> etc/dev/nginx/mime.types </summary>

```

types {
    text/html                             html htm shtml;
    text/css                              css;
    text/xml                              xml;
    image/gif                             gif;
    image/jpeg                            jpeg jpg;
    application/x-javascript              js;
    application/atom+xml                  atom;
    application/rss+xml                   rss;

    text/mathml                           mml;
    text/plain                            txt;
    text/vnd.sun.j2me.app-descriptor      jad;
    text/vnd.wap.wml                      wml;
    text/x-component                      htc;

    image/png                             png;
    image/tiff                            tif tiff;
    image/vnd.wap.wbmp                    wbmp;
    image/x-icon                          ico;
    image/x-jng                           jng;
    image/x-ms-bmp                        bmp;
    image/svg+xml                         svg svgz;
    image/webp                            webp;

    application/java-archive              jar war ear;
    application/mac-binhex40              hqx;
    application/msword                    doc;
    application/pdf                       pdf;
    application/postscript                ps eps ai;
    application/rtf                       rtf;
    application/vnd.ms-excel              xls;
    application/vnd.ms-powerpoint         ppt;
    application/vnd.wap.wmlc              wmlc;
    application/vnd.google-earth.kml+xml  kml;
    application/vnd.google-earth.kmz      kmz;
    application/x-7z-compressed           7z;
    application/x-cocoa                   cco;
    application/x-java-archive-diff       jardiff;
    application/x-java-jnlp-file          jnlp;
    application/x-makeself                run;
    application/x-perl                    pl pm;
    application/x-pilot                   prc pdb;
    application/x-rar-compressed          rar;
    application/x-redhat-package-manager  rpm;
    application/x-sea                     sea;
    application/x-shockwave-flash         swf;
    application/x-stuffit                 sit;
    application/x-tcl                     tcl tk;
    application/x-x509-ca-cert            der pem crt;
    application/x-xpinstall               xpi;
    application/xhtml+xml                 xhtml;
    application/zip                       zip;

    application/octet-stream              bin exe dll;
    application/octet-stream              deb;
    application/octet-stream              dmg;
    application/octet-stream              eot;
    application/octet-stream              iso img;
    application/octet-stream              msi msp msm;

    audio/midi                            mid midi kar;
    audio/mpeg                            mp3;
    audio/ogg                             ogg;
    audio/x-m4a                           m4a;
    audio/x-realaudio                     ra;

    video/3gpp                            3gpp 3gp;
    video/mp4                             mp4;
    video/mpeg                            mpeg mpg;
    video/quicktime                       mov;
    video/webm                            webm;
    video/x-flv                           flv;
    video/x-m4v                           m4v;
    video/x-mng                           mng;
    video/x-ms-asf                        asx asf;
    video/x-ms-wmv                        wmv;
    video/x-msvideo                       avi;
}
```

</details>

<p>
<details>
<summary> etc/dev/nginx/uwsgi_params </summary>

```

uwsgi_param  QUERY_STRING       $query_string;
uwsgi_param  REQUEST_METHOD     $request_method;
uwsgi_param  CONTENT_TYPE       $content_type;
uwsgi_param  CONTENT_LENGTH     $content_length;

uwsgi_param  REQUEST_URI        $request_uri;
uwsgi_param  PATH_INFO          $document_uri;
uwsgi_param  DOCUMENT_ROOT      $document_root;
uwsgi_param  SERVER_PROTOCOL    $server_protocol;

uwsgi_param  REMOTE_ADDR        $remote_addr;
uwsgi_param  REMOTE_PORT        $remote_port;
uwsgi_param  SERVER_PORT        $server_port;
uwsgi_param  SERVER_NAME        $server_name;
```

</details>

<p>
<details>
<summary> etc/dev/nginx/nginx.conf </summary>

```
worker_processes    auto;

error_log    stderr warn;
pid          etc/dev/tmp/nginx.pid;

events {
    worker_connections 256;
}

http {
  default_type    application/octet-stream;

  log_format ltsv "time:$time_local"
                  "\thost:$remote_addr"
                  "\tforwardedfor:$http_x_forwarded_for"
                  "\treq:$request"
                  "\tstatus:$status"
                  "\tsize:$body_bytes_sent"
                  "\treferer:$http_referer"
                  "\tua:$http_user_agent"
                  "\treqtime:$request_time"
                  "\tupsttime:$upstream_response_time"
                  "\tcache:$upstream_http_x_cache"
                  "\truntime:$upstream_http_x_runtime"
                  "\tvhost:$host";
  access_log  etc/dev/logs/access.log ltsv;

  client_body_temp_path etc/dev/tmp/client_tmp;

  sendfile    on;
  #tcp_nopush on;

  keepalive_timeout   60;
  tcp_nodelay      on;

  gzip            on;

  # uwsgi
  proxy_intercept_errors on;  # proxyがエラーを返したときに、nginxのerror_pageを適用する
  # 7秒proxyが処理を返さなければ504: GatewayTimeoutにする。
  proxy_read_timeout 7;
  proxy_connect_timeout 7;
  proxy_redirect off;

  include uwsgi_params;
  include mime.types;

  server {
      listen     7654;
      charset    utf-8;
      server_name naumanniskine.localdev;

      access_log  /dev/stdout ltsv;

      # 1リクエストの大きさを10Mまで許可する
      proxy_max_temp_file_size    0;
      client_max_body_size        10M;

      # error_pages
      error_page 404 /static/error/notfound.html;
      error_page 503 /static/error/maintenance.html;
      error_page 504 /static/error/delay.html;
      error_page 403 /static/error/forbidden.html;
      error_page 500 501 502 /static/error/error.html;

      location /static {
          alias ./static;
      }

      location / {
          root ./www;
          try_files $uri /index.html;
          default_type text/html;
      }

      location /api/ws {
        rewrite ^/api/(.+) $1 break;
        proxy_pass http://api_server/$1$is_args$args;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Server $http_host;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
      }

      location /api {
        rewrite ^/api/(.+) $1 break;
        proxy_pass http://api_server/$1$is_args$args;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Server $http_host;
        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
      }
  }

  upstream api_server {
    server 127.0.0.1:8888;
  }
}
```
</details>

### Run nginx

```
$ brew install nginx
$ mkdir -p /usr/local/var/run/nginx/proxy_temp
$ echo '127.0.0.1 naumanniskine.localdev' >> /etc/hosts
$ nginx -p `pwd` -c `pwd`/etc/dev/nginx/nginx.conf -g "daemon off;"
```

</details>
