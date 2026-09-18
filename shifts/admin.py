from django.contrib import admin

from .models import (
    PlanContract,
    PlanContractLine,
    PlannedAssemblyComponent,
    PlannedProduct,
    PlannedProductStage,
    Product,
    ProductFile,
    ProductSetup,
    ProductSetupPhoto,
    WorkContract,
    WorkContractPosition,
    WorkPositionOperation,
)


class ProductSetupPhotoInline(admin.TabularInline):
    model = ProductSetupPhoto
    extra = 0
    fields = ("setup", "image", "sort_order", "caption")


class ProductFileInline(admin.TabularInline):
    model = ProductFile
    extra = 1
    fields = ("setup", "file_type", "file", "file_name", "sort_order")
    ordering = ("sort_order", "id")


class ProductSetupInline(admin.TabularInline):
    model = ProductSetup
    extra = 0
    fields = ("name", "sort_order", "program_file")


class PlannedProductStageInline(admin.TabularInline):
    model = PlannedProductStage
    extra = 0
    ordering = ("sort_order", "id")


class PlannedAssemblyComponentInline(admin.TabularInline):
    model = PlannedAssemblyComponent
    extra = 0
    fk_name = "assembly"
    fields = ("component", "quantity", "sort_order")
    autocomplete_fields = ("component",)
    ordering = ("sort_order", "id")


class PlanContractLineInline(admin.TabularInline):
    model = PlanContractLine
    extra = 0
    autocomplete_fields = ("product",)
    ordering = ("sort_order", "id")


@admin.register(PlanContract)
class PlanContractAdmin(admin.ModelAdmin):
    list_display = ("id", "title_short", "deadline", "created_at", "updated_at")
    list_display_links = ("id", "title_short")
    search_fields = ("title",)
    date_hierarchy = "deadline"
    readonly_fields = ("created_at", "updated_at")
    inlines = (PlanContractLineInline,)

    @admin.display(description="Примечание")
    def title_short(self, obj: PlanContract) -> str:
        return (obj.title or "—")[:80]


class WorkContractPositionInline(admin.TabularInline):
    model = WorkContractPosition
    extra = 0
    ordering = ("sort_order", "id")
    fields = ("name", "quantity", "parent", "stage", "current_operation", "sort_order", "description")
    autocomplete_fields = ()
    raw_id_fields = ("current_operation", "parent")


class WorkPositionOperationInline(admin.TabularInline):
    model = WorkPositionOperation
    extra = 0
    ordering = ("sort_order", "id")


@admin.register(WorkContract)
class WorkContractAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "sort_order", "updated_at")
    list_display_links = ("id", "name")
    search_fields = ("name", "notes")
    readonly_fields = ("created_at", "updated_at")
    inlines = (WorkContractPositionInline,)


@admin.register(WorkContractPosition)
class WorkContractPositionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "contract", "quantity", "parent", "stage", "sort_order")
    list_filter = ("stage",)
    search_fields = ("name", "description", "contract__name")
    inlines = (WorkPositionOperationInline,)
    raw_id_fields = ("contract", "current_operation", "parent")


@admin.register(PlannedProduct)
class PlannedProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_assembly", "is_purchased", "workpiece_type", "created_at", "updated_at")
    list_display_links = ("id", "name")
    list_filter = ("is_assembly", "is_purchased", "workpiece_type")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (PlannedProductStageInline, PlannedAssemblyComponentInline)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = (ProductSetupInline, ProductFileInline, ProductSetupPhotoInline)
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
                    "cad_step_model",
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
