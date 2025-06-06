# buzz-with-ollama
## it's a project fork from https://github.com/chidiwilliams/buzz/tree/v1.2.0, so the install guide is same as it(and bugs...)
## i made the following changes on it.
-  You can now use a locally deployed Ollama server for subtitle translation — all API usage is free. 
-  Remove whisper.cpp(it's hard for me to generate python bindings for the whisper.cpp C/C++ library,even it's script is in makefile already)
-  save the temporary mp3 file generated during  transcribing the video file
-  change all cache and configure files to application's install directory,and remove use keyring to save openai key on macos(just save in .env file)
-  nothing else...
