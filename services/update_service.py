import json
import logging
import os
import shutil
import zipfile

import requests

import configs
from configs import path_define, ark_pixel_config, FontConfig
from configs.ark_pixel_config import SourceType
from configs.update_config import UpdateConfig
from utils import fs_util

logger = logging.getLogger('update-service')


def _get_github_releases_latest_tag_name(repository_name: str) -> str:
    url = f'https://api.github.com/repos/{repository_name}/releases/latest'
    response = requests.get(url)
    assert response.ok, url
    return response.json()['tag_name']


def _get_github_tag_sha(repository_name: str, tag_name: str) -> str:
    url = f'https://api.github.com/repos/{repository_name}/tags'
    response = requests.get(url)
    assert response.ok, url
    tag_infos = response.json()
    for tag_info in tag_infos:
        if tag_info['name'] == tag_name:
            return tag_info['commit']['sha']
    raise Exception(f"Tag info not found: '{tag_name}'")


def _get_github_branch_latest_commit_sha(repository_name: str, branch_name: str) -> str:
    url = f'https://api.github.com/repos/{repository_name}/branches/{branch_name}'
    response = requests.get(url)
    assert response.ok, url
    return response.json()['commit']['sha']


def _download_file(url: str, file_path: str):
    response = requests.get(url, stream=True)
    assert response.ok, url
    tmp_file_path = f'{file_path}.download'
    with open(tmp_file_path, 'wb') as file:
        for chunk in response.iter_content(chunk_size=512):
            if chunk is not None:
                file.write(chunk)
    os.rename(tmp_file_path, file_path)


def _save_json_file(data: dict, file_path: str):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(json.dumps(data, indent=2, ensure_ascii=False))
        file.write('\n')


def _load_json_file(file_path: str) -> dict:
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.loads(file.read())


def update_glyphs_version():
    if ark_pixel_config.source_type == SourceType.TAG:
        tag_name = ark_pixel_config.source_name
        if tag_name is None:
            tag_name = _get_github_releases_latest_tag_name(ark_pixel_config.repository_name)
        sha = _get_github_tag_sha(ark_pixel_config.repository_name, tag_name)
        version = tag_name
    elif ark_pixel_config.source_type == SourceType.BRANCH:
        branch_name = ark_pixel_config.source_name
        sha = _get_github_branch_latest_commit_sha(ark_pixel_config.repository_name, branch_name)
        version = branch_name
    elif ark_pixel_config.source_type == SourceType.COMMIT:
        sha = ark_pixel_config.source_name
        version = sha
    else:
        raise Exception(f"Unknown source type: '{ark_pixel_config.source_type}'")
    version_info = {
        'sha': sha,
        'version': version,
        'version_url': f'https://github.com/{ark_pixel_config.repository_name}/tree/{version}',
        'asset_url': f'https://github.com/{ark_pixel_config.repository_name}/archive/{sha}.zip',
    }
    file_path = os.path.join(path_define.glyphs_dir, 'version.json')
    _save_json_file(version_info, file_path)
    logger.info("Update version file: '%s'", file_path)


def setup_glyphs():
    current_version_file_path = os.path.join(path_define.ark_pixel_glyphs_dir, 'version.json')
    if os.path.isfile(current_version_file_path):
        current_sha = _load_json_file(current_version_file_path)['sha']
    else:
        current_sha = None

    version_file_path = os.path.join(path_define.glyphs_dir, 'version.json')
    version_info = _load_json_file(version_file_path)
    sha = version_info['sha']
    if current_sha == sha:
        return
    logger.info('Need setup glyphs')

    download_dir = os.path.join(path_define.cache_dir, 'ark-pixel-font', version_info['sha'])
    source_file_path = os.path.join(download_dir, 'source.zip')
    if not os.path.exists(source_file_path):
        asset_url = version_info["asset_url"]
        logger.info("Start download: '%s'", asset_url)
        fs_util.make_dirs(download_dir)
        _download_file(asset_url, source_file_path)
    else:
        logger.info("Already downloaded: '%s'", source_file_path)

    source_unzip_dir = source_file_path.removesuffix('.zip')
    fs_util.delete_dir(source_unzip_dir)
    with zipfile.ZipFile(source_file_path) as file:
        file.extractall(source_unzip_dir)
    logger.info("Unzip: '%s'", source_unzip_dir)

    fs_util.delete_dir(path_define.ark_pixel_glyphs_dir)
    fs_util.make_dirs(path_define.ark_pixel_glyphs_dir)
    for font_config in configs.font_configs:
        source_glyphs_from_dir = os.path.join(source_unzip_dir, f'ark-pixel-font-{sha}', 'assets', 'glyphs', str(font_config.size))
        if not os.path.isdir(source_glyphs_from_dir):
            continue
        source_glyphs_to_dir = os.path.join(path_define.ark_pixel_glyphs_dir, str(font_config.size))
        shutil.copytree(source_glyphs_from_dir, source_glyphs_to_dir)

        config_file_from_path = os.path.join(path_define.ark_pixel_glyphs_dir, str(font_config.size), 'config.toml')
        config_file_to_path = os.path.join(path_define.patch_glyphs_dir, str(font_config.size), 'config.toml')
        os.remove(config_file_to_path)
        os.rename(config_file_from_path, config_file_to_path)

    ark_pixel_license_dir = os.path.join(path_define.fonts_dir, 'ark-pixel')
    fs_util.delete_dir(ark_pixel_license_dir)
    fs_util.make_dirs(ark_pixel_license_dir)
    ark_pixel_license_from_path = os.path.join(source_unzip_dir, f'ark-pixel-font-{sha}', 'LICENSE-OFL')
    ark_pixel_license_to_path = os.path.join(ark_pixel_license_dir, 'LICENSE.txt')
    shutil.copyfile(ark_pixel_license_from_path, ark_pixel_license_to_path)

    fs_util.delete_dir(source_unzip_dir)
    configs.font_configs = [FontConfig(font_config.size) for font_config in configs.font_configs]
    configs.font_size_to_config = {font_config.size: font_config for font_config in configs.font_configs}
    _save_json_file(version_info, current_version_file_path)
    logger.info("Update glyphs: '%s'", sha)


def update_fonts(update_config: UpdateConfig):
    if update_config.tag_name is None:
        tag_name = _get_github_releases_latest_tag_name(update_config.repository_name)
    else:
        tag_name = update_config.tag_name
    logger.info("'%s' tag: '%s'", update_config.repository_name, tag_name)

    version = tag_name.removeprefix('v')
    repository_url = f'https://github.com/{update_config.repository_name}'

    download_dir = os.path.join(path_define.cache_dir, update_config.repository_name, tag_name)
    fs_util.make_dirs(download_dir)

    fonts_dir = os.path.join(path_define.fonts_dir, update_config.name)
    fs_util.delete_dir(fonts_dir)
    os.makedirs(fonts_dir)

    for asset_config in update_config.asset_configs:
        asset_file_name = asset_config.file_name.format(version=version)
        asset_file_path = os.path.join(download_dir, asset_file_name)
        if not os.path.exists(asset_file_path):
            asset_url = f'{repository_url}/releases/download/{tag_name}/{asset_file_name}'
            logger.info("Start download: '%s'", asset_url)
            _download_file(asset_url, asset_file_path)
        else:
            logger.info("Already downloaded: '%s'", asset_file_path)

        asset_unzip_dir = asset_file_path.removesuffix('.zip')
        fs_util.delete_dir(asset_unzip_dir)
        with zipfile.ZipFile(asset_file_path) as file:
            file.extractall(asset_unzip_dir)
        logger.info("Unzip: '%s'", asset_unzip_dir)

        for copy_info in asset_config.copy_list:
            from_path = os.path.join(asset_unzip_dir, copy_info[0].format(version=version))
            to_path = os.path.join(fonts_dir, copy_info[1].format(version=version))
            shutil.copyfile(from_path, to_path)
            logger.info("Copy from '%s' to '%s'", from_path, to_path)
        fs_util.delete_dir(asset_unzip_dir)

    version_info = {
        'repository_url': repository_url,
        'version': version,
        'version_url': f'{repository_url}/releases/tag/{tag_name}',
    }
    version_file_path = os.path.join(fonts_dir, 'version.json')
    _save_json_file(version_info, version_file_path)
    logger.info("Update version file: '%s'", version_file_path)
