from setuptools import setup

package_name = 'pupper_vision'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='142442',
    maintainer_email='noreply@example.com',
    description='カメラ画像から目的の物を見つける（YOLO-World）',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'object_detector = pupper_vision.object_detector:main',
        ],
    },
)
