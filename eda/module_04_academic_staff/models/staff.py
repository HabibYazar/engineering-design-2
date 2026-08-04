class Staff:
    def __init__(self, id, name, department, faculty, title, academic_year,
                 publication, citation, teaching_load, advising_count,
                 project_count, patent_count, admin_duty, industry_collab,
                 community_engagement):
        self.id = id
        self.name = name
        self.department = department
        self.faculty = faculty
        self.title = title
        self.academic_year = academic_year
        self.publication = publication
        self.citation = citation
        self.teaching_load = teaching_load
        self.advising_count = advising_count
        self.project_count = project_count
        self.patent_count = patent_count
        self.admin_duty = admin_duty          # True/False
        self.industry_collab = industry_collab  # True/False
        self.community_engagement = community_engagement  # 0-10 arası puan