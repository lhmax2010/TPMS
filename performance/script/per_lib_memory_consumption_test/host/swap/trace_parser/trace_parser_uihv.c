#include "trace_parser.h"
#define print_float print_int

struct uihv_obj_properties_edje_t {
	uint8_t edje_animation;
	uint8_t edje_play;
	uint32_t edje_scale;
	uint32_t edje_base_scale;
	uint32_t edje_size_min[2];
	uint32_t edje_size_max[2];

};


struct uihv_obj_properties_elementary_t {
	char *elementary_text;
	char *elementary_style;
	uint8_t elementary_disabled;
	char *elementary_widget_type;
};

struct uihv_obj_properties_common_t {
	uint32_t evas_geometry[4];
	uint8_t evas_focus;
	char *evas_name;
	uint8_t evas_visible;
	uint32_t evas_color[4];
	uint8_t evas_anti_alias;
	uint32_t evas_scale;
	uint32_t evas_size_hint_min[2];
	uint32_t evas_size_hint_max[2];
	uint32_t evas_size_hint_request[2];
	uint32_t evas_size_hint_align[2];
	uint32_t evas_size_hint_weight[2];
	uint32_t evas_size_hint_padding[4];
	uint8_t evas_render_op;
};

struct uihv_obj_properties_category_t {
	uint8_t hz;
};

struct uihv_obj_properties_specific_t {
	uint8_t hz;
};

struct uihv_obj_properties_t {
	struct uihv_obj_properties_common_t common;
	struct uihv_obj_properties_category_t category;
	struct uihv_obj_properties_specific_t specific;
};

struct uihv_obj_t {
	uint64_t addr;
	uint8_t category;
	uint32_t code;
	char *type_name;
	uint64_t rendering_time;
	uint64_t parent_addr;
	struct uihv_obj_properties_t properties;
};

struct uihv_obj_info_list_t {
	uint8_t request_option;
	uint32_t count;
};

#define parse(var, from) \
	do {\
		memcpy(&var, from, sizeof(var));\
		from += sizeof(var);\
	} while(0)

#define parse_str(var, from) \
	do {\
		var = (char *)from;\
		from += strlen(var) + 1;\
	} while(0);


/* TODO make normal specific properties parsing */
typedef void *(*parse_and_print_uihv_t)(char *p,
			     void *b,
			     const struct conversion_base *conv_base);

void *parse_and_print_uihv_obj_specific_properties_evas_unsuported(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_evas_image(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 4 + 1 + 1 + 1 + 1 + 16 + 4 + 1 + 1 + 1 + 8 + 1 + 16 + 4 + 1 +
	       1 + 4 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_evas_line(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 16;
}

void *parse_and_print_uihv_obj_specific_properties_evas_polygon(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_evas_rectangle(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_evas_text(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *st;

	parse_str(st, p);
	p += 4;
	parse_str(st, p);
	parse_str(st, p);
	p += 4 + 1 + 16 + 16 + 16 + 16 + 16 + 1;

	return p;
}

void *parse_and_print_uihv_obj_specific_properties_evas_text_block(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *st;

	parse_str(st, p);
	p += 4;
	parse_str(st, p);
	p += 1;
	parse_str(st, p);

	return p;
}

void *parse_and_print_uihv_obj_specific_properties_evas_vector(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_evas_table(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 8 + 8 + 1 + 8;
}

void *parse_and_print_uihv_obj_specific_properties_evas_box(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 8;
}

void *parse_and_print_uihv_obj_specific_properties_evas_grid(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 16;
}

void *parse_and_print_uihv_obj_specific_properties_evas_textgrid(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 8 + 8;
}

void *parse_and_print_uihv_obj_specific_properties_evas_smart(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p;
}

parse_and_print_uihv_t specific_evas[] = {
	parse_and_print_uihv_obj_specific_properties_evas_unsuported,
	parse_and_print_uihv_obj_specific_properties_evas_image,
	parse_and_print_uihv_obj_specific_properties_evas_line,
	parse_and_print_uihv_obj_specific_properties_evas_polygon,
	parse_and_print_uihv_obj_specific_properties_evas_rectangle,
	parse_and_print_uihv_obj_specific_properties_evas_text,
	parse_and_print_uihv_obj_specific_properties_evas_text_block,
	parse_and_print_uihv_obj_specific_properties_evas_vector,
	parse_and_print_uihv_obj_specific_properties_evas_table,
	parse_and_print_uihv_obj_specific_properties_evas_box,
	parse_and_print_uihv_obj_specific_properties_evas_grid,
	parse_and_print_uihv_obj_specific_properties_evas_textgrid,
	parse_and_print_uihv_obj_specific_properties_evas_smart
};

/** Elementary subtype specific properties **/
void *parse_and_print_uihv_obj_specific_properties_elementary_unsupported(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_background(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 12 + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_button(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 4 + 4 + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_check(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_colorselector(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	p += 16;
	parse_str(str, p);
	p += 1;
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_ctxpopup(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_datetime(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	parse_str(str, p);
	p += 32;
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_entry(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	parse_str(str, p);
	p += 1 + 1 + 1 + 1 + 1;
	parse_str(str, p);
	p += 1 + 1 + 1 + 1 + 1 + 4 + 1;
	parse_str(str, p);
	parse_str(str, p);
	p += 1;
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_flip(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_gengrid(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 8 + 1 + 8 + 1 + 8 + 1 + 1 + 1 + 8 + 1 + 1 + 1 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_genlist(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1 + 4 + 1 + 4 + 4 + 1 + 1 + 1 + 1 + 1 + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_glview(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 8 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_icon(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	p += 1;
	parse_str(str, p);
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_image(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 2 + 1 + 8;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_index(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1 + 4 + 1 + 4 + 1 + 4 ;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_label(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 4 + 4 + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_list(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1 + 1 + 1 + 1 + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_map(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	p += 4 + 1 + 1 + 4 + 12;
	parse_str(str, p);
	p += 4 + 1 + 4;
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_notify(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 8 + 1 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_panel(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1 + 1;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_photo(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1 + 1 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_photocam(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	p += 1;
	parse_str(str, p);
	p += 1 + 4 + 1 + 8;
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_plug(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_popup(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 8 + 1 + 1 + 1 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_progressbar(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	p += 4 + 1 + 4 + 1 + 1;
	parse_str(str, p);
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_radio(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 4 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_segmentcontrol(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_slider(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	p += 1 + 4;
	parse_str(str, p);
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_spinner(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	p += 8 + 4 + 1 + 4 + 4 + 1 + 4 + 4;
	parse_str(str, p);
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_toolbar(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	return p + 1 + 1 + 1 + 1 + 1 + 4 + 1 + 4 + 4;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_tooltip(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *str;
	parse_str(str, p);
	p += 1;
	return p;
}

void *parse_and_print_uihv_obj_specific_properties_elementary_win(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base)
{
	char *st;

	p += 1 + 1 + 1;
	parse_str(st, p);
	p += 1;
	parse_str(st, p);
	p += 8;
	parse_str(st, p);
	p += 1 + 1;
	parse_str(st, p);
	p += 1 + 1 + 4 + 1 + 1 + 4 + 1 + 1 + 4;
	parse_str(st, p);
	p += 1 + 1 + 1 + 1 + 8 + 1 + 1 + 8 + 1;
	return p;
}

parse_and_print_uihv_t specific_elementary[] = {
	parse_and_print_uihv_obj_specific_properties_elementary_unsupported, /* unsupported */
	parse_and_print_uihv_obj_specific_properties_elementary_background, /* background */
	parse_and_print_uihv_obj_specific_properties_elementary_button, /* button */
	parse_and_print_uihv_obj_specific_properties_elementary_check, /* check */
	parse_and_print_uihv_obj_specific_properties_elementary_colorselector, /* colorselector */
	parse_and_print_uihv_obj_specific_properties_elementary_ctxpopup, /* ctxpopup */
	parse_and_print_uihv_obj_specific_properties_elementary_datetime, /* datetime */
	parse_and_print_uihv_obj_specific_properties_elementary_entry, /* entry */
	parse_and_print_uihv_obj_specific_properties_elementary_flip, /* flip */
	parse_and_print_uihv_obj_specific_properties_elementary_gengrid, /* gengrid */
	parse_and_print_uihv_obj_specific_properties_elementary_genlist, /* genlist */
	parse_and_print_uihv_obj_specific_properties_elementary_glview, /* glview */
	parse_and_print_uihv_obj_specific_properties_elementary_icon, /* icon */
	parse_and_print_uihv_obj_specific_properties_elementary_image, /* image */
	parse_and_print_uihv_obj_specific_properties_elementary_index, /* index */
	parse_and_print_uihv_obj_specific_properties_elementary_label, /* label */
	parse_and_print_uihv_obj_specific_properties_elementary_list, /* list */
	parse_and_print_uihv_obj_specific_properties_elementary_map, /* map */
	parse_and_print_uihv_obj_specific_properties_elementary_notify, /* notify */
	parse_and_print_uihv_obj_specific_properties_elementary_panel, /* panel */
	parse_and_print_uihv_obj_specific_properties_elementary_photo, /* photo */
	parse_and_print_uihv_obj_specific_properties_elementary_photocam, /* photocam */
	parse_and_print_uihv_obj_specific_properties_elementary_plug, /* plug */
	parse_and_print_uihv_obj_specific_properties_elementary_popup, /* popup */
	parse_and_print_uihv_obj_specific_properties_elementary_progressbar, /* progressbar */
	parse_and_print_uihv_obj_specific_properties_elementary_radio, /* radio */
	parse_and_print_uihv_obj_specific_properties_elementary_segmentcontrol, /* segmentcontrol */
	parse_and_print_uihv_obj_specific_properties_elementary_slider, /* slider */
	parse_and_print_uihv_obj_specific_properties_elementary_spinner, /* spinner */
	parse_and_print_uihv_obj_specific_properties_elementary_toolbar, /* toolbar */
	parse_and_print_uihv_obj_specific_properties_elementary_tooltip, /* tooltip */
	parse_and_print_uihv_obj_specific_properties_elementary_win, /* win */
};

void *parse_and_print_uihv_obj_properties_specific(char __unused *p,
			     void __unused *b,
			     const struct conversion_base __unused *conv_base,
			     uint32_t __unused ui_object_code)
{
	if (ui_object_code >= 0x100 && ui_object_code < 0x200)
		p = specific_evas[ui_object_code - 0x100](p, b, conv_base);
	else if (ui_object_code >= 0x200 && ui_object_code < 0x300)
		p = specific_elementary[ui_object_code - 0x200](p, b, conv_base);

	return p;
}

////////////////////////////////////////////////////////////////////

void *parse_and_print_uihv_obj_properties_edje(void *p,
			     void *b,
			     const struct conversion_base *conv_base)
{
	struct uihv_obj_properties_edje_t edje;

	parse(edje.edje_animation, p);
	parse(edje.edje_play, p);
	parse(edje.edje_scale, p);
	parse(edje.edje_base_scale, p);
	parse(edje.edje_size_min, p);
	parse(edje.edje_size_max, p);

	conv_base->start_object(b, "edje");
	conv_base->print_int(b, "edje_animation", (uint32_t)edje.edje_animation);
	conv_base->print_int(b, "edje_play", (uint32_t)edje.edje_play);
	conv_base->print_float(b, "edje_scale", (uint32_t)edje.edje_scale);
	conv_base->print_float(b, "edje_base_scale", (uint32_t)edje.edje_base_scale);

	conv_base->print_int(b, "edje_size_min[0]", (uint32_t)edje.edje_size_min[0]);
	conv_base->print_int(b, "edje_size_min[1]", (uint32_t)edje.edje_size_min[1]);

	conv_base->print_int(b, "edje_size_max[0]", (uint32_t)edje.edje_size_max[0]);
	conv_base->print_int(b, "edje_size_max[1]", (uint32_t)edje.edje_size_max[1]);

	conv_base->finish_object(b, "edje");


	return p;
}

void *parse_and_print_uihv_obj_properties_elementary(void *p,
			     void *b,
			     const struct conversion_base *conv_base)
{
	struct uihv_obj_properties_elementary_t elm;
	parse_str(elm.elementary_text, p);
	parse_str(elm.elementary_style, p);
	parse(elm.elementary_disabled, p);
	parse_str(elm.elementary_widget_type, p);

	conv_base->start_object(b, "elementary");
	conv_base->print_str(b, "elementary_text", elm.elementary_text);
	conv_base->print_str(b, "elementary_style", elm.elementary_style);
	conv_base->print_int(b, "elementary_disabled", elm.elementary_disabled);
	conv_base->print_str(b, "elementary_widget_type", elm.elementary_widget_type);
	conv_base->finish_object(b, "elementary");

	return p;
}

void *parse_and_print_uihv_obj_properties_common(void *p,
			     void *b,
			     const struct conversion_base *conv_base)
{
	struct uihv_obj_properties_common_t common;
	parse(common.evas_geometry, p);
	parse(common.evas_focus, p);
	parse_str(common.evas_name, p);
	parse(common.evas_visible, p);
	parse(common.evas_color, p);
	parse(common.evas_anti_alias, p);
	parse(common.evas_scale, p);
	parse(common.evas_size_hint_min, p);
	parse(common.evas_size_hint_max, p);
	parse(common.evas_size_hint_request, p);
	parse(common.evas_size_hint_align, p);
	parse(common.evas_size_hint_weight, p);
	parse(common.evas_size_hint_padding, p);
	parse(common.evas_render_op, p);

	conv_base->start_object(b, "uihv_properties_common");
	conv_base->print_int(b,"evas_geometry[0]",           (uint32_t)common.evas_geometry[0]);
	conv_base->print_int(b,"evas_geometry[1]",           (uint32_t)common.evas_geometry[1]);
	conv_base->print_int(b,"evas_geometry[2]",           (uint32_t)common.evas_geometry[2]);
	conv_base->print_int(b,"evas_geometry[3]",           (uint32_t)common.evas_geometry[3]);

	conv_base->print_int(b,"evas_focus",                 (uint32_t)common.evas_focus);
	conv_base->print_str(b,"evas_name",                  common.evas_name);
	conv_base->print_int(b,"evas_visible",               (uint32_t)common.evas_visible);

	conv_base->print_int(b,"evas_color[0]",              (uint32_t)common.evas_color[0]);
	conv_base->print_int(b,"evas_color[1]",              (uint32_t)common.evas_color[1]);
	conv_base->print_int(b,"evas_color[2]",              (uint32_t)common.evas_color[2]);
	conv_base->print_int(b,"evas_color[3]",              (uint32_t)common.evas_color[3]);

	conv_base->print_int(b,"evas_anti_alias",            (uint32_t)common.evas_anti_alias);
	conv_base->print_float(b,"evas_scale",               (uint32_t)common.evas_scale);

	conv_base->print_int(b,"evas_size_hint_min[0]",      (uint32_t)common.evas_size_hint_min[0]);
	conv_base->print_int(b,"evas_size_hint_min[1]",      (uint32_t)common.evas_size_hint_min[1]);

	conv_base->print_int(b,"evas_size_hint_max[0]",      (uint32_t)common.evas_size_hint_max[0]);
	conv_base->print_int(b,"evas_size_hint_max[1]",      (uint32_t)common.evas_size_hint_max[1]);

	conv_base->print_int(b,"evas_size_hint_request[0]",  (uint32_t)common.evas_size_hint_request[0]);
	conv_base->print_int(b,"evas_size_hint_request[1]",  (uint32_t)common.evas_size_hint_request[1]);

	conv_base->print_float(b,"evas_size_hint_align[0]",    (uint32_t)common.evas_size_hint_align[0]);
	conv_base->print_float(b,"evas_size_hint_align[1]",    (uint32_t)common.evas_size_hint_align[1]);

	conv_base->print_float(b,"evas_size_hint_weight[0]",   (uint32_t)common.evas_size_hint_weight[0]);
	conv_base->print_float(b,"evas_size_hint_weight[1]",   (uint32_t)common.evas_size_hint_weight[1]);

	conv_base->print_int(b,"evas_size_hint_padding[0]",  (uint32_t)common.evas_size_hint_padding[0]);
	conv_base->print_int(b,"evas_size_hint_padding[1]",  (uint32_t)common.evas_size_hint_padding[1]);
	conv_base->print_int(b,"evas_size_hint_padding[2]",  (uint32_t)common.evas_size_hint_padding[2]);
	conv_base->print_int(b,"evas_size_hint_padding[3]",  (uint32_t)common.evas_size_hint_padding[3]);

	conv_base->print_int(b,"evas_render_op",             (uint32_t)common.evas_render_op);
	conv_base->finish_object(b, "uihv_properties_common");
	return p;
}

void *parse_and_print_uihv_obj(void *p,
			     void *b,
			     const struct conversion_base *conv_base)
{
	struct uihv_obj_t obj;

	parse(obj.addr, p);
	parse(obj.category, p);
	parse(obj.code, p);
	parse_str(obj.type_name, p);
	parse(obj.rendering_time, p);
	parse(obj.parent_addr, p);

	conv_base->start_object(b, "");

	conv_base->print_addr(b, "address", obj.addr);
	conv_base->print_int(b, "category", obj.category);
	conv_base->print_addr(b, "code", obj.code);
	conv_base->print_str(b, "type_name", obj.type_name);
	conv_base->print_time(b, "rendering_time", obj.rendering_time);
	conv_base->print_addr(b, "parent_addr", obj.parent_addr);

	p = parse_and_print_uihv_obj_properties_common(p, b, conv_base);

	if (obj.code >= 0x200 && obj.code < 0x300)
		p = parse_and_print_uihv_obj_properties_elementary(p, b, conv_base);
	else if (obj.code >= 0x300 && obj.code < 0x400)
		p = parse_and_print_uihv_obj_properties_edje(p, b, conv_base);

	p = parse_and_print_uihv_obj_properties_specific(p, b, conv_base, obj.code);

	conv_base->finish_object(b, "");
	return p;
}

void *parse_and_print_uihv_list(void *p,
			     void *b,
			     const struct conversion_base *conv_base)
{
	struct uihv_obj_info_list_t list;
	uint32_t i;

	parse(list.request_option, p);
	parse(list.count, p);

	conv_base->start_file();
	conv_base->start_object(b, "uihv_list");
	conv_base->print_int(b, "request_option", list.request_option);
	conv_base->print_int(b, "count", list.count);

	conv_base->start_object(b, "uihv_objects_list");
	for (i = 0; i < list.count; i++) {
		p = parse_and_print_uihv_obj(p, b, conv_base);
	}
	conv_base->finish_object(b, "uihv_objects_list");

	conv_base->finish_object(b, "uihv_list");
	conv_base->finish_file();
	return p;
}

int uihv_main(char __unused *buf, FILE *fd, struct parse_config_t *conf)
{
	fseek(fd, 0L, SEEK_END);
	ssize_t sz = ftell(fd);

	fseek(fd, 0L, SEEK_SET);

	void *data = malloc(sz);

	if (fread(data, sz, 1, fd) != 1) {
		conf->log("non complete header!\n");
	}
	parse_and_print_uihv_list(data, NULL, conf->conv_base);

	return 0;
}

int init_uihv(struct parse_config_t *conf) {

	fprintf(stderr, "# init_uihv\n");
	conf->main_func = uihv_main;

	return 0;
}
