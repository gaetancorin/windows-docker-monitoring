## Tutorial: Enable Email Alerts for Windows Monitoring

This tutorial explains how to enable email alerts in Grafana.
By activating this feature, you can use the **default alerts** provided, and/or create your own **custom alerts**.

## Default Alerts

By default, three alerts are preconfigured:
- When a container **stops running**
- When the global **CPU usage** is too high for more than 3 minutes
- When the global **memory usage** is too high for more than 3 minutes

## Pre-requisites

* A **Gmail account**

## How to Enable Email Alerts
1. Open the [docker-compose.yaml](docker-compose.yaml) file


2. Uncomment the following lines to activate the environment variables and alerting configuration:
```
#    env_file:
#      - .env
```
```
#    - ./grafana_provisioning/alerting:/etc/grafana/provisioning/alerting
```

3. Copy/paste [.env_example](.env_example) file and rename it to **.env**


4. Update your **.env** file with your own credentials:
- Set **GF_SMTP_USER** to your Gmail sender email address.
- Set **GF_SMTP_PASSWORD** to the **App Password** generated for your sender Gmail account. (Tutorial on how to create a Gmail App Password: [https://www.youtube.com/watch?v=MkLX85XU5rU](https://www.youtube.com/watch?v=MkLX85XU5rU))
- Set **RECEIVER** to the email address that should receive the alerts. (It can be the same as the sender email or a different email.)
- Set **GF_SMTP_HOST** to the SMTP server and port of the email receiver:
  - Gmail: `smtp.gmail.com:587`
  - Outlook: `smtp.office365.com:587`


5. Open PowerShell in the repository folder and run:
```
docker-compose up -d
```
6. Send a test email to verify your setup:
- Connect to Grafana
- Navigate to **Alerting/Contact points**
- Click on "**views**" button into the email_sender section
- Click on "**Test**" button, then click on "**Send test notification**" button

This will immediately send a test email to confirm that your configuration is working.

If you receive an error message into Grafana:  
- Stop and remove your containers.  
- Update your environment variables as needed.  
- Rebuild and restart your containers.
