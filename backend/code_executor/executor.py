# backend/code_executor/executor.py
import sys
import io
import json

class CodeExecutor:
    def __init__(self):
        # In a Cloud Run environment, we execute code directly.
        # Docker commands are not supported here.
        pass

    def execute_code(self, code, test_cases):
        """
        Executes Python code in the current process and captures output for testing.
        This is suitable for serverless environments where Docker is not available.
        """
        report = {
            "success": False,
            "output": "",
            "error_message": None,
            "exception_type": None,
            "test_results": []
        }

        # Redirect stdout to capture print statements
        old_stdout = sys.stdout
        redirected_stdout = io.StringIO()
        sys.stdout = redirected_stdout

        try:
            # Prepare a constrained environment for exec()
            # This is a basic sandbox to prevent malicious code, though not foolproof
            exec_globals = {
                '__builtins__': {
                    'print': print,
                    'len': len,
                    'list': list,
                    'dict': dict,
                    'str': str,
                    'int': int,
                    'float': float,
                    'range': range,
                    'min': min,
                    'max': max,
                    'sum': sum,
                    'sorted': sorted,
                    'reversed': reversed,
                    'set': set,
                },
                '__name__': '__main__',
                '__file__': '<string>',
            }
            exec_locals = exec_globals.copy()
            
            # Execute the AI-generated code
            exec(code, exec_globals, exec_locals)

            # Look for the 'solve' function in the executed code's local scope
            solution_func = exec_locals.get('solve')
            if not solution_func or not callable(solution_func):
                raise ValueError("Function 'solve' not found or is not a function.")
            
            all_tests_passed = True
            for i, test_case in enumerate(test_cases):
                test_result = {
                    "test_number": i + 1,
                    "input": test_case["input"],
                    "expected_output": test_case["expected_output"],
                    "actual_output": None,
                    "passed": False,
                    "error": None
                }
                
                try:
                    test_input = test_case.get("input", [])
                    actual_output = solution_func(*test_input)
                    
                    test_result["actual_output"] = json.dumps(actual_output)
                    expected_output_json = json.dumps(test_case["expected_output"])
                    
                    if test_result["actual_output"] == expected_output_json:
                        test_result["passed"] = True
                    else:
                        all_tests_passed = False
                except Exception as e:
                    test_result["error"] = str(e)
                    all_tests_passed = False
                
                report["test_results"].append(test_result)
            
            report["success"] = all_tests_passed
            report["output"] = redirected_stdout.getvalue().strip()
            
        except Exception as e:
            report["error_message"] = str(e)
            report["exception_type"] = type(e).__name__
        finally:
            sys.stdout = old_stdout
            
        return report
