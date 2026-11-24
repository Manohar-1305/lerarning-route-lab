
from dotenv import load_dotenv

load_dotenv()

import files.ansible as ansible
import files.jenkins_lab as jenkins_lab
import files.bash as bash
import files.linux as Linux
import files.auth as auth
import files.users as users
import files.contribute as contribute
import files.admin as admin
import files.subscriptions as subscriptions
import files.recommendations as recommendations

ansible.app.register_blueprint(subscriptions.bp)


if __name__ == "__main__":
    ansible.socketio.run(
        ansible.app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
