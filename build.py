import logging

import configs
from configs import path_define
from configs.dump_config import DumpConfig
from configs.fallback_config import FallbackConfig
from services import dump_service, font_service, publish_service, info_service, template_service, image_service
from utils import fs_util

logging.basicConfig(level=logging.DEBUG)


def main():
    fs_util.delete_dir(path_define.build_dir)

    dump_configs = DumpConfig.load()
    for dump_config in dump_configs:
        dump_service.dump_font(dump_config)

    fallback_configs = FallbackConfig.load()
    for fallback_config in fallback_configs:
        dump_service.apply_fallback(fallback_config)

    for font_config in configs.font_configs:
        font_service.format_patch_glyph_files(font_config)
        context = font_service.collect_glyph_files(font_config)
        for width_mode in configs.width_modes:
            font_service.make_font_files(font_config, context, width_mode)
            publish_service.make_release_zips(font_config, width_mode)
            info_service.make_info_file(font_config, context, width_mode)
            info_service.make_alphabet_txt_file(font_config, context, width_mode)
            template_service.make_alphabet_html_file(font_config, context, width_mode)
        template_service.make_demo_html_file(font_config, context)
        image_service.make_preview_image_file(font_config)
    template_service.make_index_html_file()
    template_service.make_playground_html_file()


if __name__ == '__main__':
    main()
