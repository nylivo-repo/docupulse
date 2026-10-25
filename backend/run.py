import os
import sys

import uvicorn

# Ensure backend directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings  # noqa: E402  (reads config/server.ini and environment)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        proxy_headers=True,  # honour X-Forwarded-Proto/-For from a TLS reverse proxy (Secure cookies, client address)
        forwarded_allow_ips=settings.TRUSTED_PROXIES,  # ...but only from the proxies listed in server.ini [security]
        server_header=False,  # do not advertise the server software
        log_config=None,  # the app's own logging (app.log / audit.log) handles everything
    )
