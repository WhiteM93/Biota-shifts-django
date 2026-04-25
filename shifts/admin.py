from django.contrib import admin

from .models import Product, ProductSetup, ProductSetupPhoto


class ProductSetupPhotoInline(admin.TabularInline):
    model = ProductSetupPhoto
    extra = 0
    fields = ("image", "sort_order", "caption")


class ProductSetupInline(admin.TabularInline):
    model = ProductSetup
    extra = 0
    fields = ("name", "sort_order", "program_file")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = (ProductSetupInline, ProductSetupPhotoInline)
    list_display = ("id", "name", "preview_stl_column", "created_at", "updated_at")
    list_display_links = ("id", "name")
    search_fields = ("name", "description", "setup_notes")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (
            "Файлы",
            {
                "fields": (
                    "drawing_pdf",
                    "cad_model",
                    "preview_stl",
                    "program_file",
                )
            },
        ),
        (
            "Наладка",
            {"fields": ("setup_notes",), "description": "Фото — в табе ниже."},
        ),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Превью STL")
    def preview_stl_column(self, obj: Product) -> str:
        return obj.preview_stl_list_label
