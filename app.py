from flask import Flask, request, render_template
import os
import google.generativeai as genai
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from dotenv import load_dotenv, find_dotenv

# Load environment variables
env_path = find_dotenv()
print("Loading env from", env_path)
load_dotenv(env_path)

app = Flask(__name__)

# Load credentials securely
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")
subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
credential = DefaultAzureCredential()
resource_client = ResourceManagementClient(credential, subscription_id)

# Azure resource creation functions
def create_resource_group(name, location):
    resource_client.resource_groups.create_or_update(name, {"location": location})
    return f"✅ Resource group '{name}' created in '{location}'."

def create_resource_group_resource_type(name, location):
    resource_client.resource_groups.create_or_update(name, {"location": location})
    return name

def create_storage_account(name, location):
    from azure.mgmt.storage import StorageManagementClient
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    credential = DefaultAzureCredential()
    storage_client = StorageManagementClient(credential, subscription_id)
    availability = storage_client.storage_accounts.check_name_availability({"name": name})
    if not availability.name_available:
        return f"❌ Storage account name '{name}' is not available."
    rg_name = create_resource_group_resource_type(name, location)
    print(rg_name)
    poller = storage_client.storage_accounts.begin_create(
        resource_group_name=rg_name,
        account_name=name,
        parameters={
            "location": location,
            "kind": "StorageV2",
            "sku": {"name": "Standard_LRS"}
        }
    )
    poller.result()
    return f"✅ Storage account '{name}' created in '{location}'."

def create_logic_app(name, location):
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.resource import ResourceManagementClient
    import json

    # Credentials and subscription
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    credential = DefaultAzureCredential()
    resource_client = ResourceManagementClient(credential, subscription_id)

    # Use the same name for resource group
    resource_group_name = name

    # Create resource group
    resource_client.resource_groups.create_or_update(resource_group_name, {"location": location})

    # Minimal Logic App template with placeholder logic
    logicapp_template = {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "resources": [
            {
                "type": "Microsoft.Logic/workflows",
                "apiVersion": "2019-05-01",
                "name": name,
                "location": location,
                "properties": {
                    "definition": {
                        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
                        "contentVersion": "1.0.0.0",
                        "actions": {},
                        "outputs": {},
                        "triggers": {
                            "When_a_HTTP_request_is_received": {
                "type": "Request",
                "kind": "Http",
                "inputs": {
                    "schema": {}
                }
            }
                        }
                    },
                    "parameters": {}
                }
            }
        ]
    }

    # Deployment properties
    properties = {
        "mode": "Incremental",
        "template": logicapp_template,
        "parameters": {}
    }

    # Begin deployment using poller
    try:
        poller = resource_client.deployments.begin_create_or_update(
            resource_group_name,
            f"{name}-logicapp-deployment",
            {
            "properties": {
            "mode": "Incremental",
            "template": logicapp_template,
            "parameters": {}
             }
            }
        )
        result = poller.result()
        return f"✅ Logic App '{name}' successfully deployed in '{location}'."
    except Exception as e:
        return f"❌ Failed to deploy Logic App: {e}"

def create_web_app(name, location):
    from azure.mgmt.web import WebSiteManagementClient
    from azure.mgmt.resource import ResourceManagementClient
    from azure.identity import DefaultAzureCredential
    import os

    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    credential = DefaultAzureCredential()

    # Clients
    web_client = WebSiteManagementClient(credential, subscription_id)
    resource_client = ResourceManagementClient(credential, subscription_id)

    resource_group_name = name
    app_service_plan_name = f"{name}-plan"
    web_app_name = f"{name}-web"

    # Step 1: Create or update Resource Group
    resource_client.resource_groups.create_or_update(resource_group_name, {"location": location})

    # Step 2: Create App Service Plan
    try:
        print("⏳ Creating App Service Plan...")
        poller = web_client.app_service_plans.begin_create_or_update(
            resource_group_name=resource_group_name,
            name=app_service_plan_name,
            app_service_plan={
                "location": location,
                "sku": {
                    "name": "B1",
                    "tier": "Basic",
                    "capacity": 1
                }
            }
        )
        poller.result()
    except Exception as e:
        return f"❌ Failed to create App Service Plan: {e}"

    # Step 3: Create Web App
    try:
        print("⏳ Creating Web App...")
        poller = web_client.web_apps.begin_create_or_update(
            resource_group_name=resource_group_name,
            name=web_app_name,
            site_envelope={
                "location": location,
                "server_farm_id": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Web/serverfarms/{app_service_plan_name}"
            }
        )
        poller.result()
        return f"✅ Web App '{web_app_name}' successfully created in '{location}'."
    except Exception as e:
        return f"❌ Failed to create Web App: {e}"


def create_function_app(name, location):
    from azure.mgmt.web import WebSiteManagementClient
    from azure.mgmt.storage import StorageManagementClient
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    credential = DefaultAzureCredential()

    # Initialize clients
    web_client = WebSiteManagementClient(credential, subscription_id)
    storage_client = StorageManagementClient(credential, subscription_id)

    # Step 1: Create Storage Account (required for Function App)
    try:
        availability = storage_client.storage_accounts.check_name_availability({"name": name})
        if not availability.name_available:
            print("⏳ Creating storage account...")
            poller = storage_client.storage_accounts.begin_create(
                resource_group_name=name,
                account_name=name,
                parameters={
                    "location": location,
                    "kind": "StorageV2",
                    "sku": {"name": "Standard_LRS"}
                }
            )
            poller.result()  # Wait until storage is created
    except Exception as e:
        return f"❌ Failed to create storage: {e}"

    # Step 2: Create App Service Plan (consumption plan)
    try:
        print("⏳ Creating app service plan...")
        poller = web_client.app_service_plans.begin_create_or_update(
            resource_group_name=name,
            name=f"{name}-plan",
            app_service_plan={
                "location": location,
                "sku": {
                            "name": "Y1",
                            "tier": "Dynamic"
                        },
                        "kind": "functionapp",
                        "reserved": False
            }
        )
        poller.result()
    except Exception as e:
        return f"❌ Failed to create app service plan: {e}"

    # Step 3: Create Function App
    try:
        print("⏳ Creating Function App...")
        poller = web_client.web_apps.begin_create_or_update(
            resource_group_name=name,
            name=f"{name}-func",
            site_envelope={
                "location": location,
                "server_farm_id": f"/subscriptions/{subscription_id}/resourceGroups/{name}/providers/Microsoft.Web/serverfarms/{name}-plan",
                "kind": "functionapp",
                "site_config": {
                    "app_settings": [
                        {"name": "AzureWebJobsStorage", "value": f"DefaultEndpointsProtocol=https;AccountName={name};AccountKey=***REPLACE_THIS***;EndpointSuffix=core.windows.net"},
                        {"name": "FUNCTIONS_EXTENSION_VERSION", "value": "~4"},
                        {"name": "FUNCTIONS_WORKER_RUNTIME", "value": "python"}
                    ]
                }
            }
        )
        poller.result()
        return f"✅ Function App '{name}-func' successfully created in '{location}'."
    except Exception as e:
        return f"❌ Failed to create Function App: {e}"




@app.route("/", methods=["GET", "POST"])
def index():
    result = ""
    if request.method == "POST":
        user_prompt = request.form.get("message")

        # Gemini system prompt
        system_prompt = """
You are an Azure cloud assistant.
Your job is to extract deployment information from user commands related to Azure resource creation.

Supported resource types:
- Resource Group (RG)
- Virtual Machine (VM)
- Storage Account
- Web App
- Function App
- Logic App


Your output must be in the following format:

resource_type: <resource-type>
name: <resource-name>
location: <azure-region>

Rules:
- Always lowercase resource_type
- Only include one resource per response
- No explanations, just return data in exact format
- If unclear, default to "resource group"
"""

        try:
            full_prompt = system_prompt + f"\n\nCommand:\n\"{user_prompt}\""
            response = model.generate_content(full_prompt)
            parsed = response.text.strip().lower()

            resource_type = parsed.split("resource_type:")[1].split("name:")[0].strip()
            name = parsed.split("name:")[1].split("location:")[0].strip()
            location = parsed.split("location:")[1].strip()

            if "resource group" in resource_type:
                result = create_resource_group(name, location)
            elif "storage account" in resource_type:
                result = create_storage_account(name, location)
            elif "function app" in resource_type:
                result = create_function_app(name, location)
            elif "web app" in resource_type:
                result = create_web_app(name, location)
            elif "logic app" in resource_type:
                result = create_logic_app(name, location)
            elif "Web app" in resource_type:
                result = create_web_app(name, location)
            else:
                result = f"❌ Unknown resource type '{resource_type}'."

        except Exception as e:
            result = f"❌ Error: {e}"

    return render_template("index.html", result=result)

if __name__ == "__main__":
    app.run(debug=True)
