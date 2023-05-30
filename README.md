
# Music-recommendation-system

The goal of this project is to develop an intelligent music recommendation system that can provide personalized song recommendations to users based on their musical preferences. The system will take into account various factors such as user preferences, song genres, artist similarity, and user listening history to generate accurate and relevant recommendations.

# Tech Stack

* Python 
* Deepface
* Matplotlib
* Opencv
* Spotipy

## Installation

# DeepFace
The easiest way to install deepface is to download it from [`PyPI`](https://pypi.org/project/deepface/). It's going to install the library itself and its prerequisites as well.

```shell
$ pip install deepface
```

Secondly, DeepFace is also available at [`Conda`](https://anaconda.org/conda-forge/deepface). You can alternatively install the package via conda.

```shell
$ conda install -c conda-forge deepface
```

Thirdly, you can install deepface from its source code.

```shell
$ git clone https://github.com/serengil/deepface.git
$ cd deepface
$ pip install -e .
```

Then you will be able to import the library and use its functionalities.

```python
from deepface import DeepFace
```

# Matplotlib


See the [install
documentation](https://matplotlib.org/stable/users/installing/index.html),
which is generated from `/doc/users/installing/index.rst`

# OpenCV

On Windows and MacOS, the package can be installed directoy from CRAN:

```r
install.packages("opencv")
```

### Install from source

To install from source on MacOS, you need to install the opencv library from homebrew:

```sh
brew install opencv
```

On Ubuntu or Fedora you need [`libopencv-dev`](https://packages.debian.org/testing/libopencv-dev) or [`opencv-devel`](https://src.fedoraproject.org/rpms/opencv):

```sh
sudo apt-get install libopencv-dev
```

For Ubuntu 16.04 (Xenial) and Ubuntu 18.04 (Bionic) we provide [a PPA](https://launchpad.net/~cran/+archive/ubuntu/opencv) with more recent versions of OpenCV:

```sh
sudo add-apt-repository ppa:cran/opencv
sudo apt-get install libopencv-dev
```

And then install the R bindings:

```r
install.packages("opencv", type = "source")
```
# Spotipy

```bash
pip install spotipy
```

alternatively, for Windows users 

```bash
py -m pip install spotipy
```

or upgrade

```bash
pip install spotipy --upgrade
```
