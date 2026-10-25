# download and import flask library or fastapi, whatever you want for your backend
# download and import jinja or equivalent for
# templating and serving your html, css, and javascript files (if you plan to have a frontend)

print("BEST OF LUCK")

app = FLASK() # or whatever syntax you use to initialize a flask app

app.post("/sensor/data")
def notify_stakeholders():
    # some logic to send emails saying 
    # some bin is full to relevant people
    # dont build from this code, ha e shapo
    pass