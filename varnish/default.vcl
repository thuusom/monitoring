# varnish/default.vcl

vcl 4.0;

backend apache {
    .host = "apache_server";
    .port = "80";
    .probe = {
        .url = "/";
        .timeout = 1s;         # Wait 1 second for a response
        .interval = 5s;        # Probe every 5 seconds
        .window = 5;           # Use the last 5 probes to calculate health
        .threshold = 3;        # Require at least 3 successful probes
    }
}

backend nginx {
    .host = "nginx_server";
    .port = "80";
    .probe = {
        .url = "/";
        .timeout = 1s;
        .interval = 5s;
        .window = 5;
        .threshold = 3;
    }
}
sub vcl_recv {
    if (req.url ~ "^/apache") {
        set req.backend_hint = apache;
        set req.url = regsub(req.url, "^/apache", "");  # Remove the /apache prefix
    } else {
        set req.backend_hint = nginx;
    }
}