from flask import Flask, render_template, request, session, redirect, jsonify
import os
import pyrebase
import base64


app = Flask(__name__)
app.secret_key = "secret_key"
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')



# Configure your Firebase credentials
config = {    

}

firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
storage = firebase.storage()
db = firebase.database()  


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.create_user_with_email_and_password(email, password)
            session['email'] = email
            return redirect('/dashboard')
        except Exception as e:
            error = str(e)
            return render_template('signup.html', error=error)
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session['email'] = email
            session['user_token'] = user['idToken']  # Save the idToken into the session
            return redirect('/home')
        except Exception as e:
            error = str(e)
            return render_template('login.html', error=error)
    return render_template('login.html')



@app.route('/home')
def home():
    if 'email' in session:         
        return render_template('index.html')
    else:
        return redirect('/login')



from datetime import datetime

@app.route('/upload', methods=['POST'])
def handle_data():
    data = request.get_json()

    file_name = data.get('fileName')
    image_base64s = data.get('imageUrls', [])

    dir_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    for i, image_base64 in enumerate(image_base64s):
        prefix, image_base64 = image_base64.split(";base64,")
        img_data = base64.b64decode(image_base64)

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')

        local_file_path = os.path.join(dir_path, f'image_{timestamp}.png')
        with open(local_file_path, 'wb') as f:
            f.write(img_data)

        file_path = f"{file_name}/image_{timestamp}.png"
        storage.child("{}/{}".format(session['email'], file_path)).put(local_file_path)

        url = storage.child("{}/{}".format(session['email'], file_path)).get_url(None)
        data = {"email": session['email'], "folder_name": file_name, "file_name": f"image_{timestamp}.png", "url": url}
        db.child("user_files").push(data)

        os.remove(local_file_path)

    return jsonify({'message': 'Uploaded Successfully!'})




#@app.route('/service-worker.js')
#def sw():
    #return app.send_static_file('service-worker.js')



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)), debug=False)
