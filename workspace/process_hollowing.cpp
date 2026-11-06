#include <iostream>
#include <windows.h>
#include <tlhelp32.h>
#include <vector>
#include <string>
#include <fstream>

using namespace std;

// Function to hollow a process
bool hollow_process(const std::string& target_process_name) {
    HANDLE hProcess = NULL;
    PROCESSENTRY32 pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32);

    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnap != INVALID_HANDLE_VALUE) {
        if (Process32First(hSnap, &pe32)) {
            do {
                if (strcmp(pe32.szExeFile, target_process_name.c_str()) == 0) {
                    cout << "Found process: " << pe32.szExeFile << endl;
                    hProcess = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pe32.th32ProcessId);
                    if (hProcess) {
                        cout << "Successfully opened process ID: " << pe32.th32ProcessId << endl;
                        // In a real scenario, you would inject code here.
                        // For this example, we just simulate the hollow action.
                        cout << "Simulating process hollowing for " << target_process_name << "..." << endl;
                        // Actual hollowing involves:
                        // 1. Allocating memory in the target process.
                        // 2. Writing shellcode into that memory.
                        // 3. Creating a remote thread to execute the shellcode.
                        
                        // For demonstration, we will just close the handle after simulation
                        CloseHandle(hProcess);
                        cout << "Process hollowing simulation complete for " << target_process_name << "." << endl;
                        return true;
                    }
                }
            } while (Process32Next(hSnap, &pe32));
        }
    }
    CloseHandle(hSnap);
    return false;
}

int main() {
    string target_process = "notepad.exe";
    cout << "Attempting to hollow " << target_process << "..." << endl;
    
    if (hollow_process(target_process)) {
        cout << "Process hollowing operation finished." << endl;
    } else {
        cout << "Could not find or hollow the process: " << target_process << endl;
    }

    cout << "Press Enter to exit." << endl;
    cin.get();
    return 0;
}