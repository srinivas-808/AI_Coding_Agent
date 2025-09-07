# backend/code_executor/executor.py
import subprocess
import os
import json
import shutil
import uuid

class CodeExecutor:
    def __init__(self):
        self.language_config = {
            "docker_image": "python-coder-env",
            "runner_script": "runner.py",
            "code_file_name": "generated_code.py"
        }
        self.temp_dir_prefix = "ai_agent_code_run_"

    def _prepare_temp_directory(self, generated_code, test_cases_json, unique_id):
        """
        Prepares a temporary directory with the generated code, runner script, and test cases.
        Returns the path to the temporary directory.
        """
        config = self.language_config
        
        # Get the directory of the app.py (the entry point)
        # This ensures temp directories are created in the main backend folder
        app_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) # Go up one level from code_executor
        
        temp_path = os.path.join(app_base_dir, self.temp_dir_prefix + unique_id)
        os.makedirs(temp_path, exist_ok=True)

        # Write the generated code to the appropriate file name
        with open(os.path.join(temp_path, config["code_file_name"]), "w") as f:
            f.write(generated_code)

        # Copy the correct runner script for Python
        current_module_dir = os.path.dirname(__file__) # Directory where executor.py is
        shutil.copy(os.path.join(current_module_dir, config["runner_script"]), temp_path)

        # Write the test cases to 'test_cases.json'
        with open(os.path.join(temp_path, "test_cases.json"), "w") as f:
            json.dump(test_cases_json, f, indent=4)

        return temp_path

    def _cleanup_temp_directory(self, temp_path):
        """Removes the temporary directory."""
        if os.path.exists(temp_path):
            shutil.rmtree(temp_path)

    def execute_code(self, generated_code, test_cases, language="python"):
        """
        Executes the generated code with provided test cases in a Docker container.
        Returns a dictionary containing the execution report.
        (Language parameter is ignored for now, always assumes Python).
        """
        unique_id = str(uuid.uuid4())
        temp_dir = None
        
        if language != "python":
            return {
                "success": False,
                "output": "",
                "error_message": f"Only 'python' language is supported in this version. Got '{language}'.",
                "exception_type": "UnsupportedLanguage",
                "test_results": []
            }

        config = self.language_config

        try:
            temp_dir = self._prepare_temp_directory(generated_code, test_cases, unique_id)

            docker_command = [
                "docker", "run", "--rm",
                "-v", f"{temp_dir}:/app",
                config["docker_image"],
                "python", config["runner_script"]
            ]

            print(f"Executing Docker command: {' '.join(docker_command)}")

            process = subprocess.run(
                docker_command,
                capture_output=True,
                text=True,
                check=False
            )

            raw_output = process.stdout.strip()

            try:
                report = json.loads(raw_output)
                return report
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "output": raw_output,
                    "error_message": f"Execution environment error (runner output was not valid JSON or stderr had issues): {process.stderr.strip()}",
                    "exception_type": "DockerExecutionError",
                    "test_results": []
                }

        except FileNotFoundError:
            return {
                "success": False,
                "output": "",
                "error_message": "Docker command not found. Is Docker installed and in your PATH?",
                "exception_type": "DockerNotFound",
                "test_results": []
            }
        except ValueError as ve:
            return {
                "success": False,
                "output": "",
                "error_message": str(ve),
                "exception_type": "ValueError",
                "test_results": []
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error_message": f"An unexpected error occurred during Docker execution: {type(e).__name__}: {str(e)}",
                "exception_type": type(e).__name__,
                "test_results": []
            }
        finally:
            if temp_dir:
                self._cleanup_temp_directory(temp_dir)
