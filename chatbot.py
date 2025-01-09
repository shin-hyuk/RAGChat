import sys
import os
import requests
from dotenv import load_dotenv
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QLabel, QMessageBox, QTextEdit, QPushButton, QComboBox, QHBoxLayout
from PyQt5.QtCore import QTimer

# Base folder for accessing .env and data folder dynamically
base_folder = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
env_path = os.path.join(base_folder, ".env")
data_folder = os.path.join(base_folder, "data")

# Load environment function for dynamic access
def load_environment():
    load_dotenv(dotenv_path=env_path, override=True)
    return {
        "API_BASE_URL": os.getenv("API_BASE_URL"),
        "API_TOKEN": os.getenv("API_TOKEN"),
        "WORKSPACE_SLUG": os.getenv("WORKSPACE_SLUG")
    }

# Access latest .env values
env = load_environment()
API_BASE_URL = env["API_BASE_URL"]
API_TOKEN = env["API_TOKEN"]
WORKSPACE_SLUG = env["WORKSPACE_SLUG"]

class LoginApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setGeometry(300, 300, 400, 200)

        # Set up layout
        layout = QVBoxLayout()
        layout.setSpacing(20)

        # Username input
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        layout.addWidget(self.username_input)

        # Password input
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        # Bind Enter key to login
        self.password_input.returnPressed.connect(self.login)

        # Main widget container
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Input Error", "Please enter both username and password.")
            return

        # Step 1: Send login request to /request-token
        token_url = f"{API_BASE_URL}/request-token"
        headers = {"Content-Type": "application/json"}
        payload = {"username": username, "password": password}

        try:
            response = requests.post(token_url, headers=headers, json=payload)
            response.raise_for_status()
            response_json = response.json()
        except (requests.RequestException, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Failed to authenticate user. {e}")
            return
        
        # Extract role from the response
        try:
            role = response_json['user']['role']  # Get role from nested user object
        except KeyError:
            # Raise an error if the role is not found
            raise ValueError("Role information is missing in the response.")

        # Check role and proceed based on role type
        if role == "default":
            self.fetch_workspaces(username)
        elif role == "admin":
            self.fetch_workspaces()  # No username required for admin
        else:
            raise ValueError(f"Unexpected role '{role}' found in the response.")


    def fetch_workspaces(self, username=None):
        workspaces_url = f"{API_BASE_URL}/v1/workspaces"
        headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

        workspaces_response = requests.get(workspaces_url, headers=headers)
        if workspaces_response.status_code != 200:
            QMessageBox.critical(self, "Error", "Failed to fetch workspaces.")
            return

        workspaces_data = workspaces_response.json()['workspaces']
        user_workspaces = []

        if username:  # Fetch for default role user
            for workspace in workspaces_data:
                workspace_id = workspace['id']
                workspace_users_url = f"{API_BASE_URL}/v1/admin/workspaces/{workspace_id}/users"
                workspace_users_response = requests.get(workspace_users_url, headers=headers)

                if workspace_users_response.status_code == 200:
                    users_in_workspace = workspace_users_response.json().get("users", [])
                    for workspace_user in users_in_workspace:
                        if workspace_user['username'] == username:
                            user_workspaces.append(workspace)
                            break
        else:
            user_workspaces = workspaces_data  # For admin, add all workspaces

        if user_workspaces:
            self.open_chat_interface(user_workspaces)
        else:
            QMessageBox.warning(self, "Access Denied", "You do not have access to any workspace.")

    def open_chat_interface(self, user_workspaces):
        self.chat_window = ChatApp(user_workspaces)
        self.chat_window.show()
        self.close()

class ChatApp(QMainWindow):
    def __init__(self, workspaces):
        super().__init__()
        self.setWindowTitle("Chatbot Interface")
        self.setGeometry(300, 300, 500, 400)

        # Set up main layout
        layout = QVBoxLayout()

        # Workspace dropdown
        self.workspace_selector = QComboBox()
        self.workspace_dict = {workspace['name']: workspace['slug'] for workspace in workspaces}
        self.workspace_selector.addItems(self.workspace_dict.keys())
        self.workspace_selector.currentTextChanged.connect(self.change_workspace)
        layout.addWidget(self.workspace_selector)

        # Row layout for Upload Data and Reset Chat buttons
        button_row_layout = QHBoxLayout()

        # Upload Data button
        upload_button = QPushButton("Upload Data")
        upload_button.clicked.connect(self.upload_data)
        button_row_layout.addWidget(upload_button)

        # Reset Chat button
        reset_button = QPushButton("Reset Chat")
        reset_button.clicked.connect(self.reset_chat)
        button_row_layout.addWidget(reset_button)

        layout.addLayout(button_row_layout)  # Add button row to main layout

        # Chat display area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)

        # User input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter your message here...")
        self.input_field.returnPressed.connect(self.send_message)
        layout.addWidget(self.input_field)

        # Main widget container
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Set initial workspace slug in .env
        self.update_env_variable("WORKSPACE_SLUG", self.workspace_dict[self.workspace_selector.currentText()])

    def change_workspace(self, workspace_name):
        workspace_slug = self.workspace_dict.get(workspace_name)
        if workspace_slug:
            self.update_env_variable("WORKSPACE_SLUG", workspace_slug)
            self.chat_display.clear()

    def upload_data(self):
        self.loading_message = QMessageBox(self)
        self.loading_message.setWindowTitle("Uploading Data")
        self.loading_message.setText("Data is being uploaded. Please wait.")
        self.loading_message.setStandardButtons(QMessageBox.NoButton)
        self.loading_message.show()

        QTimer.singleShot(10, self.run_update_data_script)

    def run_update_data_script(self):
        upload_all_files()
        self.loading_message.hide()

    def reset_chat(self):
        self.input_field.setText("/reset")
        self.send_message()

    def send_message(self):
        user_message = self.input_field.text()
        if user_message == "/reset":
            # Clear the chat display and show "Chat History Cleared"
            self.chat_display.clear()
            self.input_field.clear()
        elif user_message:
            # Show the user message immediately
            self.chat_display.append(f"You: {user_message}")
            self.input_field.clear()

        # Delay the bot's response by 200 ms (0.2 seconds) to show the user message instantly
        QTimer.singleShot(10, lambda: self.fetch_and_display_response(user_message))

    def fetch_and_display_response(self, user_message):
        # Fetch the response and display it
        response_text = self.get_chat_response(user_message)
        self.chat_display.append(f"Bot: {response_text}")

    def get_chat_response(self, message):
        load_dotenv(dotenv_path=env_path, override=True)

        chat_url = f"{API_BASE_URL}/v1/workspace/{os.getenv('WORKSPACE_SLUG')}/chat"
        print(chat_url)
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {"message": message, "mode": "chat", "sessionId": "unique-session-id"}
        try:
            print(chat_url)
            print(headers)
            print(payload)
            response = requests.post(chat_url, headers=headers, json=payload)
            if response.status_code == 200:
                response_json = response.json()
                if response_json.get("error") is not None:
                    return f"Error: {response_json['error']}"
                return response_json.get("textResponse", "No response text available")
            else:
                return f"Failed to connect. Status code: {response.status_code}"
        except requests.RequestException as e:
            return f"Error: {e}"

    def update_env_variable(self, key, value):
        """Helper method to update .env file with a new value for a specific key."""
        with open(env_path, 'r') as file:
            lines = file.readlines()
        with open(env_path, 'w') as file:
            for line in lines:
                if line.startswith(key + "="):
                    file.write(f"{key}={value}\n")
                else:
                    file.write(line)
        load_dotenv(dotenv_path=env_path, override=True)

# Rename files in the data folder, replacing spaces with underscores
def rename_files_in_data_folder():
    for root, _, files in os.walk(data_folder):
        for file_name in files:
            if " " in file_name:
                old_file_path = os.path.join(root, file_name)
                new_file_name = file_name.replace(" ", "_")
                new_file_path = os.path.join(root, new_file_name)
                os.rename(old_file_path, new_file_path)
                print(f"Renamed '{old_file_path}' to '{new_file_path}'")

# Fetch existing documents in the workspace
def fetch_workspace_documents():
    workspace_url = f"{API_BASE_URL}/v1/workspace/{WORKSPACE_SLUG}"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    response = requests.get(workspace_url, headers=headers)
    if response.status_code == 200:
        response_json = response.json()
        return [doc['docpath'] for doc in response_json['workspace'][0].get('documents', [])]
    else:
        print("Error fetching documents.")
        return []

# Upload a single file and add its location to adds_list
def upload_file(file_path, adds_list):
    upload_url = f"{API_BASE_URL}/v1/document/upload"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    with open(file_path, 'rb') as file_data:
        response = requests.post(upload_url, headers=headers, files={'file': (os.path.basename(file_path), file_data)})
    if response.status_code == 200:
        location = response.json()['documents'][0]['location']
        adds_list.append(location)
    else:
        print(f"Failed to upload {file_path}")

# Update embeddings for the workspace
def update_embeddings(adds_list, deletes_list):
    env = load_environment()  # Reload .env to ensure latest WORKSPACE_SLUG
    update_url = f"{env['API_BASE_URL']}/v1/workspace/{env['WORKSPACE_SLUG']}/update-embeddings"
    print(update_url)
    headers = {
        "Authorization": f"Bearer {env['API_TOKEN']}",
        "Content-Type": "application/json"
    }
    data = {"adds": adds_list, "deletes": deletes_list}
    response = requests.post(update_url, headers=headers, json=data)
    if response.status_code != 200:
        print("Failed to update embeddings.")

# Remove documents from the workspace
def remove_documents(documents_to_remove):
    remove_url = f"{API_BASE_URL}/v1/system/remove-documents"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    data = {"names": documents_to_remove}
    response = requests.post(remove_url, headers=headers, json=data)
    if response.status_code != 200:
        print("Failed to remove documents.")

# Main function to process all files in the data folder
def upload_all_files():
    # Rename files in the data folder, replacing spaces with underscores
    rename_files_in_data_folder()

    # Fetch existing documents in the workspace
    workspace_docpaths = fetch_workspace_documents()
    deletes_list = []

    # Prepare a list of files to upload
    files_to_upload = []
    for root, _, files in os.walk(data_folder):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            if os.path.isfile(file_path):
                if any(file_name in docpath for docpath in workspace_docpaths):
                    deletes_list.append(next(docpath for docpath in workspace_docpaths if file_name in docpath))
                files_to_upload.append(file_path)

    # Remove old documents
    if deletes_list:
        remove_documents(deletes_list)

    # Upload each file in the data folder
    adds_list = []
    for file_path in files_to_upload:
        upload_file(file_path, adds_list)

    # Update embeddings
    if adds_list:
        update_embeddings(adds_list, deletes_list)
    else:
        print("No new files detected. Embeddings remain up-to-date.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    login_window = LoginApp()
    login_window.show()
    sys.exit(app.exec_()) 