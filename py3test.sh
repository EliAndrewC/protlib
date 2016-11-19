cd `dirname $0`

mkdir -p py3
cd py3
cp ../protlib.py ../unit_tests.py .
2to3 --write protlib.py unit_tests.py
python3 unit_tests.py
