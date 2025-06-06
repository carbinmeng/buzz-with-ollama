# buzz-with-ollama
## it's a project fork from https://github.com/chidiwilliams/buzz/tree/v1.2.0, so the install guide is same as it(and bugs...)
## i made the following changes on it.
-  You can now use a locally deployed Ollama server for subtitle translation — all API usage is free. 
-  Remove whisper.cpp(it's hard for me to generate python bindings for the whisper.cpp C/C++ library,even it's script is in makefile already)
-  save the temporary mp3 file generated during  transcribing the video file
-  change all cache and configure files to application's install directory,and remove use keyring to save openai key on macos(just save in .env file)
-  nothing else...
-  


# install guide
# on mac os
```shell 
# install ffmepg
brew install ffmpeg@6

# install pyenv(for download specific version of python)
brew install pyenv

# install python 
pyenv install 3.12.9

# configue the project to use the python,will create file .python-version
cd "this project directory"
pyenv local 3.12.9

# create the virtual enviroment
poetry init
poetry env info -p # get the path to the virtual environment

# install dependencies on pyproject.toml (preferably using poetry.lock). 
poetry install

# create .env file
cp .env.sample .env

# run buzz use virtual enviroment
poetry  run python -m buzz

```

# prompt for tanslate to english using model like qwen3 that can be turn off the "thinking"
Please translate the following subtitle segment into natural, fluent English. Each segment provided is in sequence and continues the meaning of the previous content, so be sure to translate it in context. Ensure the translation is accurate, smooth, and contextually appropriate. **Do not** include any explanations or comments—just return the translated English text only.\n/no_think


