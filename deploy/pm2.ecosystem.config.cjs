// Alternative to systemd — run as dscapi user:
//   cd /opt/dscapi && pm2 start deploy/pm2.ecosystem.config.cjs
//   pm2 save

module.exports = {
  apps: [
    {
      name: 'dscapi',
      cwd: '/opt/dscapi',
      script: '/opt/dscapi/venv/bin/gunicorn',
      args: 'DSCApi.wsgi:application --bind 127.0.0.1:8081 --workers 2 --timeout 120',
      interpreter: 'none',
      env: {
        DJANGO_SETTINGS_MODULE: 'DSCApi.settings',
      },
      env_file: '/opt/dscapi/.env',
      user: 'dscapi',
      autorestart: true,
      max_restarts: 10,
    },
  ],
};
