#email.py
import smtplib
from email.mime.text import MIMEText



def send_mail(msg,mail_sender,pw_sender, email_recipient):
    s = smtplib.SMTP('smtp.web.de', 587)
    # start TLS for security
    s.starttls()
    # Authentication
    s.login(mail_sender, pw_sender)
    msg= MIMEText(msg)
    msg['Subject'] = 'Your Product Feedback'
    msg['From'] = 'fragenfabrik@web.de'
    msg['To'] = email_recipient
    s.send_message(msg)
    s.quit()