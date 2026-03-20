Clone https://github.com/google/xls

Clone https://github.com/kokke/tiny-AES-C in ./AES

Remove git from ./AES and ./xls

Create a repo in my github account and push the code to it.

Create a new branch called seting-up-the-environment

In a folder called ./AES-trojan, do the following:
I want you to create a platform using:
- Chipwhisperer husky (which is connected)
- Google XLS (which is cloned and compiled)
- Vivado (which is installed)

Google XLS will be used to generate RTL code from ./AES
Vivado will be used to synthesize the RTL code and generate a bitstream using TCL scripts.
The bitstream will be uploaded to the CW312-A35 Artix A7 35T through the CW313 board of the HUSKY.

Create one script to perform HLS using Google XLS of the TinyAES C++ description. If necessary change the code of TinyAES so that it is 
synthesizable by Google XLS.
One script to perform synthesis and implementation of the RTL code produced by Google XLSusing Vivado.
One script to upload the bitstream to the CW312-A35 Artix A7 35T through the CW313 board of the HUSKY.

All files and folders should be organized in a logical manner under ./AES-trojan.

Create a python script to communicate with the AES and perform encryption/decryption operations.
The plaintext/ciphertext and key should be configurable and provided by the CLI with an argument indicating the operation (encrypt/decrypt).
The script should save the sent data and the received data in a .mat file and in a json file.

Use the pycryptodome library for encryption/decryption so as to verify the correctness of the implementation by comparing the results.

Place a trigger signifying to the HUSKY when to start sampling and when to stop sampling - one active high pulse at the relevant pin of the HUSKY.

The HUSKY should be able to be configured regarding the sampling rate and all the relevant settings through the CLI.
The power traces should be saved in the .mat file so that they correspond to the sent and received data.

Document everything.

Do not stop unless it works perfectly.






































































































































