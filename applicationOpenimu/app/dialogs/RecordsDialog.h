#include<QDialog>
#include<QPushButton>
#include<QLabel>
#include<QGridLayout>
#include<QLineEdit>
#include<QComboBox>
#include "core/components/blockType/DbBlock.h"

class RecordsDialog : public QDialog
{
    Q_OBJECT

public:

    RecordsDialog(QWidget *parent=0);
    ~RecordsDialog();

private slots:

    void selectRecordSlot();
    void addRecordSlot();

  private:

    QPushButton *selectRecord;
    QString folderToAdd;
    QLabel* folderSelected;
    QPushButton *addRecord;
    QGridLayout *mainLayout;
    QLabel* recordNaming;
    QLineEdit *recordName;
    QComboBox* imuSelectComboBox;
    DbBlock * databaseAccess;
    QLabel* selectedImu;
    QLabel* successLabel;
    QComboBox* imuPositionComboBox;
    QLabel* imuPosition;
    QLabel* recordDetails;
    QLineEdit* userDetails;
};